"""
orchestrator.py — Main Multi-Agent evaluation pipeline coordinator with concurrency limits, idempotence, and self-learning loop.
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions

try:
    from .models import (
        AccuracyResult,
        CaseEvalSummary,
        CsvDiffResult,
        DependencyType,
        PatchVerificationResult,
        QualityResult,
        RunResult,
        TraceMetrics,
        TraceSpan,
        calculate_llm_cost,
        grade_to_score,
    )
    from .sandbox import SandboxProvider, create_sandbox
    from .guardrails import BadDepsStore
    from .storage import AtomicJsonStorage, ReportGenerator
    from .mcp_tools import (
        create_guardrail_mcp_server,
        create_patch_mcp_server,
        create_sandbox_mcp_server,
    )
    from .agents import (
        get_accuracy_evaluator_agent,
        get_auto_learner_agent,
        get_auto_repair_agent,
        get_csv_diff_agent,
        get_quality_evaluator_agent,
        get_runtime_evaluator_agent,
    )
except (ImportError, ValueError):
    from models import (
        AccuracyResult,
        CaseEvalSummary,
        CsvDiffResult,
        DependencyType,
        PatchVerificationResult,
        QualityResult,
        RunResult,
        TraceMetrics,
        TraceSpan,
        calculate_llm_cost,
        grade_to_score,
    )
    from sandbox import SandboxProvider, create_sandbox
    from guardrails import BadDepsStore
    from storage import AtomicJsonStorage, ReportGenerator
    from mcp_tools import (
        create_guardrail_mcp_server,
        create_patch_mcp_server,
        create_sandbox_mcp_server,
    )
    from agents import (
        get_accuracy_evaluator_agent,
        get_auto_learner_agent,
        get_auto_repair_agent,
        get_csv_diff_agent,
        get_quality_evaluator_agent,
        get_runtime_evaluator_agent,
    )

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Collected response data from one Claude Agent request."""

    text: str = ""
    structured_output: Any = None
    model_usage: Dict[str, Any] = field(default_factory=dict)
    total_cost_usd: float = 0.0
    elapsed_seconds: float = 0.0
    is_error: bool = False
    error: str = ""


def _message_text(message: Any) -> str:
    """Extract visible text from an SDK message without depending on one SDK version."""
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks = []
        for block in content:
            text = getattr(block, "text", None)
            if isinstance(text, str) and text:
                chunks.append(text)
        return "\n".join(chunks)
    return ""


def _extract_json_payload(value: Any) -> Optional[Dict[str, Any]]:
    """Extract the first JSON object from structured output or Markdown text."""
    if isinstance(value, dict):
        for wrapper_key in ("structured_output", "structuredOutput"):
            wrapped = value.get(wrapper_key)
            if isinstance(wrapped, dict):
                return wrapped
        return value
    if not isinstance(value, str):
        return None

    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            return candidate
    return None


def _score_to_grade(score: float) -> int:
    """Map a 0-100 score to the project's 1-5 anchored grade."""
    return max(1, min(5, int(float(score) // 20)))


def _normalise_dynamic_payload(
    payload: Dict[str, Any], result_type: Type[Any]
) -> Dict[str, Any]:
    """Validate required dynamic fields and derive omitted aggregate values."""
    data = dict(payload)
    if result_type is not PatchVerificationResult:
        if not isinstance(data.get("status"), str):
            raise ValueError("Agent output must include a string field: status")
        data["status"] = data["status"].strip().lower()
        if data["status"] not in {"success", "fail", "skipped"}:
            raise ValueError(f"Unsupported result status: {data['status']}")

    if result_type in {AccuracyResult, QualityResult}:
        dimensions = data.get("dimensions") or []
        if not isinstance(dimensions, list):
            raise ValueError("dimensions must be a JSON array")
        dimension_scores = []
        normalised_dimensions = []
        for dimension in dimensions:
            if not isinstance(dimension, dict):
                continue
            item = dict(dimension)
            if "score" not in item and "grade" in item:
                item["score"] = grade_to_score(int(item["grade"]))
            if "grade" not in item and "score" in item:
                item["grade"] = _score_to_grade(float(item["score"]))
            if "score" in item:
                dimension_scores.append(float(item["score"]))
            normalised_dimensions.append(item)
        data["dimensions"] = normalised_dimensions

        if "overall_score" not in data:
            if not dimension_scores:
                raise ValueError("Agent output must include overall_score or scored dimensions")
            data["overall_score"] = round(sum(dimension_scores) / len(dimension_scores), 2)
        data["overall_score"] = max(0.0, min(100.0, float(data["overall_score"])))
        if "overall_grade" not in data:
            data["overall_grade"] = _score_to_grade(data["overall_score"])
        return data

    if result_type is CsvDiffResult:
        if "matched_ratio" not in data:
            missing = data.get("missing_items") or []
            unexpected = data.get("unexpected_items") or []
            total = len(missing) + len(unexpected)
            data["matched_ratio"] = 1.0 if total == 0 else 0.0
        data["matched_ratio"] = max(0.0, min(1.0, float(data["matched_ratio"])))
        return data

    if result_type is RunResult:
        if "exit_code" not in data:
            data["exit_code"] = 0 if data["status"] == "success" else 1
        data["exit_code"] = int(data["exit_code"])
        return data

    if result_type is PatchVerificationResult:
        return data

    return data


def parse_dynamic_result(
    response: AgentResponse, result_type: Type[Any]
) -> Any:
    """Parse and Pydantic-validate a dynamic Agent result."""
    candidates = [response.structured_output, response.text]
    payload = None
    for candidate in candidates:
        payload = _extract_json_payload(candidate)
        if payload is not None:
            break
    if payload is None:
        raise ValueError("Agent did not return a JSON object")
    data = _normalise_dynamic_payload(payload, result_type)
    return result_type.model_validate(data)


class EvalOrchestrator:
    """Coordinates multi-stage evaluations across cases with semaphore rate limiting."""

    def __init__(
        self,
        work_dir: str,
        sandbox: Optional[SandboxProvider] = None,
        bad_deps_store_path: Optional[str] = None,
        max_concurrency: int = 5,
        slow_fail_threshold_seconds: float = 120.0,
        enable_auto_repair: bool = True,
        allow_automatic_repair: bool = False,
        model_name: Optional[str] = None,
    ):
        self.work_dir = Path(work_dir)
        self.sandbox = sandbox or create_sandbox("utm")
        self.bad_deps_store = BadDepsStore(
            bad_deps_store_path or str(self.work_dir / "bad_deps.json")
        )
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.slow_fail_threshold = slow_fail_threshold_seconds
        self.enable_auto_repair = enable_auto_repair
        self.allow_automatic_repair = allow_automatic_repair
        self.model_name = model_name
        self._invalid_cache_case_ids: set[str] = set()

        self.sandbox_server = create_sandbox_mcp_server(self.sandbox)
        self.guardrail_server = create_guardrail_mcp_server(self.bad_deps_store)
        self.patch_server = create_patch_mcp_server()
        self.mcp_servers = {
            "sandbox": self.sandbox_server,
            "guardrails": self.guardrail_server,
            "patch_tools": self.patch_server,
        }

    def _agent_options(
        self,
        agent_name: str,
        agent_def: Any,
        result_type: Optional[Type[Any]] = None,
        include_mcp: bool = False,
        patch_root: Optional[str] = None,
    ) -> ClaudeAgentOptions:
        kwargs: Dict[str, Any] = {
            "allowed_tools": agent_def.tools,
            "agents": {agent_name: agent_def},
            "model": self.model_name,
        }
        # 留空时让 SDK 自动选择发行包内置的 Claude Code CLI；只有显式配置
        # CLAUDE_CLI_PATH 时才覆盖它，避免要求使用者另外安装 claude 命令。
        cli_path = os.getenv("CLAUDE_CLI_PATH", "").strip()
        if cli_path:
            kwargs["cli_path"] = cli_path
        if include_mcp:
            mcp_servers = self.mcp_servers
            if patch_root:
                mcp_servers = {
                    **self.mcp_servers,
                    "patch_tools": create_patch_mcp_server(allowed_root=patch_root),
                }
            kwargs["mcp_servers"] = mcp_servers
        if result_type is not None:
            kwargs["output_format"] = {
                "type": "json_schema",
                "schema": result_type.model_json_schema(),
            }
        return ClaudeAgentOptions(**kwargs)

    async def _query_agent(
        self,
        prompt: str,
        agent_name: str,
        agent_def: Any,
        result_type: Optional[Type[Any]] = None,
        include_mcp: bool = False,
        patch_root: Optional[str] = None,
    ) -> AgentResponse:
        """Run one Agent and retain text, structured output, usage, and errors."""
        started = time.time()
        response = AgentResponse()
        options = self._agent_options(
            agent_name=agent_name,
            agent_def=agent_def,
            result_type=result_type,
            include_mcp=include_mcp,
            patch_root=patch_root,
        )
        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)
                text_parts: List[str] = []
                async for message in client.receive_response():
                    text = _message_text(message)
                    result_text = getattr(message, "result", None)
                    if isinstance(result_text, str) and result_text:
                        text = f"{text}\n{result_text}" if text else result_text
                    if text:
                        text_parts.append(text)
                    structured = getattr(message, "structured_output", None)
                    if structured is not None:
                        response.structured_output = structured
                    model_usage = getattr(message, "model_usage", None)
                    if isinstance(model_usage, dict) and model_usage:
                        response.model_usage = model_usage
                    else:
                        usage = getattr(message, "usage", None)
                        if isinstance(usage, dict) and usage:
                            response.model_usage = {"__reported__": usage}
                    cost = getattr(message, "total_cost_usd", None)
                    if isinstance(cost, (int, float)):
                        response.total_cost_usd = float(cost)
                    if getattr(message, "is_error", False):
                        response.is_error = True
                    if getattr(message, "errors", None):
                        response.error = "; ".join(str(item) for item in message.errors)
                response.text = "\n".join(text_parts).strip()
        except Exception as exc:
            response.is_error = True
            response.error = str(exc)
        response.elapsed_seconds = time.time() - started
        return response

    @staticmethod
    def _usage_int(usage: Dict[str, Any], *keys: str) -> int:
        """Read the first available integer usage field across provider formats."""
        for key in keys:
            value = usage.get(key)
            if value is not None:
                try:
                    return max(0, int(value))
                except (TypeError, ValueError):
                    continue
        return 0

    @classmethod
    def _record_trace(
        cls,
        metrics: TraceMetrics,
        stage_name: str,
        response: AgentResponse,
        span_type: str = "llm_agent",
    ) -> None:
        input_tokens = 0
        output_tokens = 0
        cache_hit_input_tokens = 0
        cache_miss_input_tokens = 0
        cache_creation_input_tokens = 0
        cost_usd = response.total_cost_usd
        reported_cost_usd = 0.0
        model_name = metrics.model_name
        if response.model_usage:
            usage_keys = [key for key in response.model_usage if key != "__reported__"]
            if usage_keys:
                model_name = usage_keys[0]
            for usage in response.model_usage.values():
                if not isinstance(usage, dict):
                    continue
                output_tokens += cls._usage_int(usage, "outputTokens", "output_tokens", "completion_tokens")
                cache_hit = cls._usage_int(
                    usage,
                    "cacheReadInputTokens",
                    "cache_read_input_tokens",
                    "prompt_cache_hit_tokens",
                )
                cache_creation = cls._usage_int(
                    usage,
                    "cacheCreationInputTokens",
                    "cache_creation_input_tokens",
                )
                explicit_cache_miss = cls._usage_int(
                    usage,
                    "cacheMissInputTokens",
                    "cache_miss_input_tokens",
                    "prompt_cache_miss_tokens",
                )
                prompt_tokens = cls._usage_int(usage, "prompt_tokens")
                base_input_tokens = cls._usage_int(usage, "inputTokens", "input_tokens")
                is_prompt_total_format = "prompt_tokens" in usage or any(
                    key in usage
                    for key in (
                        "prompt_cache_hit_tokens",
                        "prompt_cache_miss_tokens",
                    )
                )
                has_explicit_cache_miss = any(
                    key in usage
                    for key in (
                        "cacheMissInputTokens",
                        "cache_miss_input_tokens",
                        "prompt_cache_miss_tokens",
                    )
                )

                # Claude/Anthropic usage reports input_tokens as the uncached
                # portion; cached reads and cache writes are separate buckets.
                # DeepSeek-style prompt_tokens is already the total prompt
                # count and normally includes explicit hit/miss fields.
                if is_prompt_total_format:
                    total_input = prompt_tokens or base_input_tokens
                    input_tokens += total_input
                    cache_miss_input_tokens += (
                        explicit_cache_miss
                        if has_explicit_cache_miss
                        else max(0, total_input - cache_hit)
                    )
                elif cache_hit or cache_creation or any(
                    key in usage
                    for key in (
                        "cacheReadInputTokens",
                        "cache_read_input_tokens",
                        "cacheCreationInputTokens",
                        "cache_creation_input_tokens",
                    )
                ):
                    input_tokens += base_input_tokens + cache_hit + cache_creation
                    cache_miss_input_tokens += (
                        explicit_cache_miss
                        if has_explicit_cache_miss
                        else base_input_tokens + cache_creation
                    )
                else:
                    input_tokens += base_input_tokens
                    cache_miss_input_tokens += explicit_cache_miss

                cache_hit_input_tokens += cache_hit
                cache_creation_input_tokens += cache_creation
                for cost_key in ("costUSD", "cost_usd"):
                    if usage.get(cost_key) is not None:
                        try:
                            reported_cost_usd += max(0.0, float(usage[cost_key]))
                        except (TypeError, ValueError):
                            pass
                        break

        cost_usd = max(cost_usd, reported_cost_usd)
        if input_tokens <= 0:
            input_tokens = cache_hit_input_tokens + cache_miss_input_tokens
        observed_cache_input = cache_hit_input_tokens + cache_miss_input_tokens
        cache_hit_rate = (
            cache_hit_input_tokens / observed_cache_input
            if observed_cache_input > 0
            else None
        )

        if cost_usd <= 0 and (input_tokens or output_tokens):
            cost_usd = calculate_llm_cost(model_name, input_tokens, output_tokens)
        metrics.model_name = model_name
        metrics.total_input_tokens += input_tokens
        metrics.total_output_tokens += output_tokens
        metrics.total_tokens += input_tokens + output_tokens
        metrics.cache_hit_input_tokens += cache_hit_input_tokens
        metrics.cache_miss_input_tokens += cache_miss_input_tokens
        metrics.cache_creation_input_tokens += cache_creation_input_tokens
        metrics.total_cost_usd += cost_usd
        total_cache_input = (
            metrics.cache_hit_input_tokens + metrics.cache_miss_input_tokens
        )
        metrics.cache_hit_rate = (
            metrics.cache_hit_input_tokens / total_cache_input
            if total_cache_input > 0
            else None
        )
        metrics.spans.append(
            TraceSpan(
                name=stage_name,
                span_type=span_type,
                status="fail" if response.is_error else "success",
                elapsed_seconds=response.elapsed_seconds,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                cache_hit_input_tokens=cache_hit_input_tokens,
                cache_miss_input_tokens=cache_miss_input_tokens,
                cache_creation_input_tokens=cache_creation_input_tokens,
                cache_hit_rate=cache_hit_rate,
                cost_usd=cost_usd,
                details=response.error or "Dynamic structured result collected.",
            )
        )

    @staticmethod
    def _raw_response(response: AgentResponse) -> str:
        raw = response.text or response.error
        return raw[:12000]

    async def run_pipeline_for_case(self, case_id: str) -> CaseEvalSummary:
        """Execute all stages for a single case under concurrency semaphore."""
        async with self.semaphore:
            start_time = time.time()
            case_dir = self.work_dir / case_id
            logger.info("[%s] Starting evaluation pipeline in %s", case_id, case_dir)
            existing_trace = AtomicJsonStorage.load(
                str(case_dir / "trace_metrics.json"), TraceMetrics
            )
            cache_is_compatible = not self.model_name or (
                existing_trace is not None
                and existing_trace.model_name == self.model_name
            )
            if not cache_is_compatible:
                self._invalid_cache_case_ids.add(case_id)
                existing_trace = None
            else:
                self._invalid_cache_case_ids.discard(case_id)
            summary = CaseEvalSummary(
                case_id=case_id,
                trace_metrics=existing_trace
                or TraceMetrics(model_name=self.model_name or "unknown"),
            )
            if not case_dir.exists():
                logger.warning("[%s] Directory does not exist, skipping.", case_id)
                summary.overall_verdict = "SKIPPED"
                return summary

            gt_dir = case_dir / "gt"
            has_gt = gt_dir.exists() and any(gt_dir.iterdir())
            summary.task_type = "understanding" if has_gt else "generation"
            trace = summary.trace_metrics

            hit_bad_dep = self.bad_deps_store.check_project_for_bad_deps(str(case_dir))
            run_result_path = str(case_dir / "eval_run_result.json")
            if hit_bad_dep and not AtomicJsonStorage.is_completed(run_result_path, RunResult):
                logger.info("[%s] [FAST-FAIL] Hit known bad dependency: %s", case_id, hit_bad_dep.id)
                summary.run_result = RunResult(
                    status="fail",
                    exit_code=1,
                    run_method="static_analysis",
                    log_summary=(
                        f"Static fast-fail: {hit_bad_dep.dep_type.value} "
                        f"package {hit_bad_dep.dep_name} known missing."
                    ),
                    error_snippet=f"Dependency {hit_bad_dep.dep_name} not found in registry.",
                    note=f"Matched guardrail rule: {hit_bad_dep.reason}",
                    elapsed_seconds=0.1,
                )
                AtomicJsonStorage.save(run_result_path, summary.run_result)
                trace.spans.append(
                    TraceSpan(
                        name="runtime",
                        span_type="static",
                        status="fail",
                        elapsed_seconds=0.1,
                        details=summary.run_result.note,
                    )
                )
            else:
                summary.run_result = await self._run_stage_runtime(case_id, str(case_dir), trace)

            if (
                summary.run_result
                and summary.run_result.status == "fail"
                and summary.run_result.elapsed_seconds > self.slow_fail_threshold
            ):
                await self._trigger_auto_learning(case_id, summary.run_result.error_snippet, trace)

            summary.accuracy_result = await self._run_stage_accuracy(case_id, str(case_dir), trace)
            summary.quality_result = await self._run_stage_quality(case_id, str(case_dir), trace)
            if has_gt:
                summary.csv_diff_result = await self._run_stage_csv_diff(
                    case_id, str(case_dir), str(gt_dir), trace
                )

            if (
                self.enable_auto_repair
                and self.allow_automatic_repair
                and summary.run_result
                and summary.run_result.status == "fail"
            ):
                summary.patch_result = await self._run_stage_auto_repair(
                    case_id, str(case_dir), summary, trace
                )
                AtomicJsonStorage.save(
                    str(case_dir / "patch_result.json"), summary.patch_result
                )

            total_elapsed = time.time() - start_time
            summary.total_elapsed_seconds = total_elapsed
            trace.total_elapsed_seconds = total_elapsed
            AtomicJsonStorage.save(str(case_dir / "trace_metrics.json"), trace)
            run_ok = bool(summary.run_result and summary.run_result.status == "success")
            acc_ok = bool(
                summary.accuracy_result
                and summary.accuracy_result.status == "success"
                and summary.accuracy_result.overall_score >= 60.0
            )
            quality_ok = bool(
                summary.quality_result
                and summary.quality_result.status == "success"
                and summary.quality_result.overall_score >= 60.0
            )
            csv_ok = not summary.csv_diff_result or (
                summary.csv_diff_result.status == "success"
                and summary.csv_diff_result.matched_ratio >= 0.8
            )
            summary.overall_verdict = "PASS" if run_ok and acc_ok and quality_ok and csv_ok else "FAIL"
            AtomicJsonStorage.save(str(case_dir / "case_summary.json"), summary)
            logger.info(
                "[%s] Completed in %.1fs — Verdict: %s",
                case_id,
                total_elapsed,
                summary.overall_verdict,
            )
            return summary

    async def _run_stage_runtime(
        self, case_id: str, case_dir: str, trace: TraceMetrics
    ) -> RunResult:
        out_path = os.path.join(case_dir, "eval_run_result.json")
        cached = (
            AtomicJsonStorage.load(out_path, RunResult)
            if case_id not in self._invalid_cache_case_ids
            else None
        )
        if cached:
            trace.spans.append(
                TraceSpan(name="runtime", span_type="cached", status=cached.status, details="Cached result")
            )
            return cached

        agent_def = get_runtime_evaluator_agent(model=self.model_name)
        prompt = f"""
请对测试用例目录进行真实构建与运行验证：{case_dir}

要求：
1. 阅读 {case_dir}/task.md 了解原始需求，阅读项目源码和依赖清单。
2. 根据技术栈选择最小且有代表性的安装、编译、测试或启动命令，并通过 sandbox 工具执行。
3. 不要修改待测项目，不要把评测结果文件当作源码依据。
4. 最终只返回一个 JSON 对象，必须包含 status（success 或 fail）、exit_code、attempt_count、log_summary、error_snippet、run_method、note、inspect_cmd、elapsed_seconds。
5. status 必须反映真实执行结果；任何构建/测试/启动失败都必须为 fail，并在 error_snippet 中保留关键错误。
""".strip()
        response = await self._query_agent(
            prompt, "runtime_evaluator", agent_def, RunResult, include_mcp=True
        )
        self._record_trace(trace, "runtime", response)
        try:
            result = parse_dynamic_result(response, RunResult)
            if response.is_error and result.status == "success":
                result.status = "fail"
                result.exit_code = 1
                result.error_snippet = response.error or "Agent reported an execution error."
            result.run_method = result.run_method or "llm_agent"
            if not result.elapsed_seconds:
                result.elapsed_seconds = response.elapsed_seconds
        except Exception as exc:
            result = RunResult(
                status="fail",
                exit_code=1,
                run_method="llm_agent",
                error_snippet=response.error or self._raw_response(response),
                log_summary=f"Runtime result parsing failed: {exc}",
                note="Agent output did not satisfy the RunResult JSON contract.",
                elapsed_seconds=response.elapsed_seconds,
            )
        AtomicJsonStorage.save(out_path, result)
        return result

    async def _run_stage_accuracy(
        self, case_id: str, case_dir: str, trace: TraceMetrics
    ) -> AccuracyResult:
        out_path = os.path.join(case_dir, "eval_accuracy.json")
        cached = (
            AtomicJsonStorage.load(out_path, AccuracyResult)
            if case_id not in self._invalid_cache_case_ids
            else None
        )
        if cached:
            trace.spans.append(
                TraceSpan(name="accuracy", span_type="cached", status=cached.status, details="Cached result")
            )
            return cached

        agent_def = get_accuracy_evaluator_agent(model=self.model_name)
        prompt = f"""
请独立评审代码功能与逻辑准确性：{case_dir}

评审输入：
- 原始需求：{case_dir}/task.md
- 待测源码：{case_dir}/mnt（如实际源码在其子目录，请自行识别）

规则：
1. 只能依据原始需求和待测源码评分；不要读取或参考 eval_*.json、eval/output.* 等评测产物。
2. 检查功能完整性、核心逻辑、边界条件、异常路径和需求遗漏。
3. 严格按照 1-5 档评级，分数应与维度证据一致。
4. 最终只返回一个 JSON 对象，必须包含 status、overall_grade、overall_score、dimensions、strengths、weaknesses、repair_suggestions。
5. dimensions 中每项必须包含 dimension、grade、score、reason；status 只能是 success 或 fail。
""".strip()
        response = await self._query_agent(
            prompt, "accuracy_evaluator", agent_def, AccuracyResult
        )
        self._record_trace(trace, "accuracy", response)
        try:
            result = parse_dynamic_result(response, AccuracyResult)
            if response.is_error:
                result.status = "fail"
                result.raw_output = response.error or result.raw_output
            else:
                result.raw_output = self._raw_response(response)
        except Exception as exc:
            result = AccuracyResult(
                status="fail",
                overall_grade=1,
                overall_score=0.0,
                raw_output=(response.error or self._raw_response(response))[:12000],
                weaknesses=[f"动态准确性结果解析失败：{exc}"],
            )
        AtomicJsonStorage.save(out_path, result)
        return result

    async def _run_stage_quality(
        self, case_id: str, case_dir: str, trace: TraceMetrics
    ) -> QualityResult:
        out_path = os.path.join(case_dir, "eval_quality.json")
        cached = (
            AtomicJsonStorage.load(out_path, QualityResult)
            if case_id not in self._invalid_cache_case_ids
            else None
        )
        if cached:
            trace.spans.append(
                TraceSpan(name="quality", span_type="cached", status=cached.status, details="Cached result")
            )
            return cached

        agent_def = get_quality_evaluator_agent(model=self.model_name)
        prompt = f"""
请对代码目录进行动态工程质量评审与根因归因：{case_dir}

评审输入：
- 原始需求：{case_dir}/task.md
- 待测源码：{case_dir}/mnt（如实际源码在其子目录，请自行识别）

请从架构与工程规范、运行时健壮性、性能与安全防线、交付体验与可观测性四个支柱审查，并结合任务需求判断 UX/交付完整性。
不要读取或参考 eval_*.json、eval/output.* 等评测产物。
最终只返回一个 JSON 对象，必须包含 status、overall_grade、overall_score、dimensions、code_structure_analysis、strengths、weaknesses、repair_suggestions。
dimensions 中每项必须包含 name、grade、score、comment；status 只能是 success 或 fail。所有扣分都要给出可定位的证据或明确理由。
""".strip()
        response = await self._query_agent(
            prompt, "quality_evaluator", agent_def, QualityResult
        )
        self._record_trace(trace, "quality", response)
        try:
            result = parse_dynamic_result(response, QualityResult)
            if response.is_error:
                result.status = "fail"
                result.raw_output = response.error or result.raw_output
            else:
                result.raw_output = self._raw_response(response)
        except Exception as exc:
            result = QualityResult(
                status="fail",
                overall_grade=1,
                overall_score=0.0,
                raw_output=(response.error or self._raw_response(response))[:12000],
                weaknesses=[f"动态质量结果解析失败：{exc}"],
            )
        AtomicJsonStorage.save(out_path, result)
        return result

    async def _run_stage_csv_diff(
        self, case_id: str, case_dir: str, gt_dir: str, trace: TraceMetrics
    ) -> CsvDiffResult:
        out_path = os.path.join(case_dir, "eval_csv_diff.json")
        cached = (
            AtomicJsonStorage.load(out_path, CsvDiffResult)
            if case_id not in self._invalid_cache_case_ids
            else None
        )
        if cached:
            trace.spans.append(
                TraceSpan(name="csv_diff", span_type="cached", status=cached.status, details="Cached result")
            )
            return cached

        agent_def = get_csv_diff_agent(model=self.model_name)
        prompt = f"""
请对生成产物和标准答案做细粒度差异比较。
- 用例目录：{case_dir}
- 生成产物目录：{case_dir}/mnt
- Ground Truth 目录：{gt_dir}

先检查字段/列结构，再比较行、条目和数值误差。最终只返回一个 JSON 对象，必须包含 status、matched_ratio、diff_summary、missing_items、unexpected_items、raw_output。
matched_ratio 必须是 0 到 1 之间的小数；status 只能是 success 或 fail。没有可比较的结构化产物时必须说明原因，并按此事实给出结果，不得固定返回 1.0。
""".strip()
        response = await self._query_agent(
            prompt, "csv_diff_evaluator", agent_def, CsvDiffResult
        )
        self._record_trace(trace, "csv_diff", response)
        try:
            result = parse_dynamic_result(response, CsvDiffResult)
            result.raw_output = self._raw_response(response)
            if response.is_error:
                result.status = "fail"
        except Exception as exc:
            result = CsvDiffResult(
                status="fail",
                matched_ratio=0.0,
                diff_summary=f"动态差异结果解析失败：{exc}",
                raw_output=(response.error or self._raw_response(response))[:12000],
            )
        AtomicJsonStorage.save(out_path, result)
        return result

    async def execute_authorized_repair(
        self,
        case_id: str,
        summary: CaseEvalSummary,
        human_guidance: str = "",
    ) -> PatchVerificationResult:
        """Run an explicitly human-authorized repair without rerunning cached stages."""
        case_dir = self.work_dir / case_id
        trace = summary.trace_metrics or TraceMetrics(model_name=self.model_name or "unknown")
        patch_result = await self._run_stage_auto_repair(
            case_id,
            str(case_dir),
            summary,
            trace,
            human_guidance=human_guidance,
        )
        summary.patch_result = patch_result
        trace.total_elapsed_seconds += trace.spans[-1].elapsed_seconds if trace.spans else 0.0
        summary.trace_metrics = trace
        AtomicJsonStorage.save(str(case_dir / "patch_result.json"), patch_result)
        AtomicJsonStorage.save(str(case_dir / "trace_metrics.json"), trace)
        AtomicJsonStorage.save(str(case_dir / "case_summary.json"), summary)
        return patch_result

    async def _run_stage_auto_repair(
        self,
        case_id: str,
        case_dir: str,
        summary: CaseEvalSummary,
        trace: TraceMetrics,
        human_guidance: str = "",
    ) -> PatchVerificationResult:
        agent_def = get_auto_repair_agent(model=self.model_name)
        prompt = f"""
请根据以下评测结果判断是否需要自动修复用例：{case_dir}

运行结果：{summary.run_result.model_dump_json() if summary.run_result else "null"}
准确性结果：{summary.accuracy_result.model_dump_json() if summary.accuracy_result else "null"}
质量结果：{summary.quality_result.model_dump_json() if summary.quality_result else "null"}

        上层调用已明确授权本次修复。追加指导（可能为空）：{human_guidance or "无"}
        只有在修复建议明确、补丁范围可控时才修改代码。目标源码位于 {case_dir}/mnt（请自行识别其实际子目录），不要修改 eval_*.json、trace_metrics.json 或 case_summary.json。
        修改后必须在本地沙箱中执行与项目相关的最小回归检查，并如实记录是否真的写入了源码、是否复测通过。最终只返回一个 JSON 对象，包含 patch_applied、run_after_patch_passed、score_improved、old_score、new_score、verification_log。
""".strip()

        response = await self._query_agent(
            prompt,
            "auto_repair",
            agent_def,
            PatchVerificationResult,
            include_mcp=True,
            patch_root=str(Path(case_dir) / "mnt"),
        )
        self._record_trace(trace, "auto_repair", response)
        try:
            result = parse_dynamic_result(response, PatchVerificationResult)
            if response.is_error and not result.verification_log:
                result.verification_log = response.error or "Auto-repair agent reported an error."
            # Scores returned by the repair agent are advisory only; this path
            # does not rerun the evaluators, so never persist them as verified.
            result.score_improved = False
            result.old_score = None
            result.new_score = None
            return result
        except Exception as exc:
            return PatchVerificationResult(
                verification_log=f"动态自动修复结果解析失败：{exc}; {response.error or self._raw_response(response)[:4000]}"
            )

    async def _trigger_auto_learning(
        self, case_id: str, error_snippet: str, trace: TraceMetrics
    ) -> None:
        logger.info("[%s] Triggering self-learning from slow failure...", case_id)
        agent_def = get_auto_learner_agent(model=self.model_name)
        prompt = f"""
分析以下构建失败信息，判断是否为 Maven/npm/pip 中不存在的依赖：
{error_snippet[:4000]}

如果是坏依赖，调用 guardrail 工具记录；否则只回复 NOT_A_BAD_DEP。不要修改项目代码。
""".strip()
        response = await self._query_agent(
            prompt, "auto_learner", agent_def, include_mcp=True
        )
        self._record_trace(trace, "auto_learning", response)

    async def run_batch(self, case_ids: List[str]) -> List[CaseEvalSummary]:
        """Run the entire evaluation batch concurrently and generate reports."""
        summaries = await asyncio.gather(
            *(self.run_pipeline_for_case(case_id) for case_id in case_ids)
        )
        eval_dir = self.work_dir / "eval"
        ReportGenerator.generate_markdown_summary(summaries, str(eval_dir / "output.md"))
        ReportGenerator.generate_html_dashboard(summaries, str(eval_dir / "output_viz.html"))
        return summaries
