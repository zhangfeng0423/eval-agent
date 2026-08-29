"""
test_storage.py — Unit tests for AtomicJsonStorage, schema validation, and report generation.
"""

import asyncio
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

from claude_agent_sdk import ModelUsage, ResultMessage

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from models import (
    AccuracyResult,
    CaseEvalSummary,
    CsvDiffResult,
    QualityResult,
    RunResult,
    TraceMetrics,
)
from orchestrator import AgentResponse, EvalOrchestrator, parse_dynamic_result
from storage import AtomicJsonStorage, ReportGenerator


class TestStorage(unittest.TestCase):

    def test_atomic_json_storage_success(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            path = f.name

        try:
            run_res = RunResult(
                status="success",
                exit_code=0,
                log_summary="Build succeeded",
                elapsed_seconds=12.5
            )
            AtomicJsonStorage.save(path, run_res)
            
            loaded = AtomicJsonStorage.load(path, RunResult)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.status, "success")
            self.assertEqual(loaded.exit_code, 0)
            self.assertEqual(loaded.elapsed_seconds, 12.5)
            self.assertTrue(AtomicJsonStorage.is_completed(path, RunResult))
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_atomic_json_storage_invalid_schema(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("corrupted json {")
            path = f.name

        try:
            self.assertIsNone(AtomicJsonStorage.load(path, RunResult))
            self.assertFalse(AtomicJsonStorage.is_completed(path, RunResult))
        finally:
            if os.path.exists(path):
                os.remove(path)

    def test_dynamic_accuracy_result_parsing(self):
        response = AgentResponse(
            text="```json\n{\"status\":\"success\",\"dimensions\":[{\"dimension\":\"核心功能\",\"grade\":5,\"reason\":\"完整\"}],\"strengths\":[],\"weaknesses\":[],\"repair_suggestions\":[]}\n```"
        )
        result = parse_dynamic_result(response, AccuracyResult)
        self.assertEqual(result.overall_score, 100.0)
        self.assertEqual(result.overall_grade, 5)
        self.assertEqual(result.dimensions[0].score, 100.0)

    def test_dynamic_csv_diff_result_parsing(self):
        response = AgentResponse(
            structured_output={
                "status": "success",
                "matched_ratio": 0.75,
                "diff_summary": "one mismatch",
                "missing_items": ["a"],
                "unexpected_items": [],
            }
        )
        result = parse_dynamic_result(response, CsvDiffResult)
        self.assertEqual(result.matched_ratio, 0.75)
        self.assertEqual(result.missing_items, ["a"])

    def test_query_agent_captures_real_sdk_cache_usage(self):
        sdk_usage: ModelUsage = {
            "inputTokens": 120,
            "outputTokens": 30,
            "cacheReadInputTokens": 480,
            "cacheCreationInputTokens": 80,
            "webSearchRequests": 0,
            "costUSD": 0.0042,
            "contextWindow": 200000,
            "maxOutputTokens": 4096,
        }
        sdk_message = ResultMessage(
            subtype="success",
            duration_ms=10,
            duration_api_ms=8,
            is_error=False,
            num_turns=1,
            session_id="test-session",
            model_usage={"deepseek-v4-flash": sdk_usage},
            total_cost_usd=0.0042,
            result="structured result",
        )

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_value, traceback):
                return False

            async def query(self, prompt):
                return None

            async def receive_response(self):
                yield sdk_message

        orchestrator = EvalOrchestrator.__new__(EvalOrchestrator)
        orchestrator.model_name = "deepseek-v4-flash"
        with patch("orchestrator.ClaudeSDKClient", return_value=FakeClient()), patch.object(
            orchestrator, "_agent_options", return_value=object()
        ):
            response = asyncio.run(
                orchestrator._query_agent(
                    "test prompt", "test-agent", agent_def=object()
                )
            )

        metrics = TraceMetrics(model_name="deepseek-v4-flash")
        EvalOrchestrator._record_trace(metrics, "quality", response)

        self.assertEqual(response.text, "structured result")
        self.assertEqual(response.model_usage["deepseek-v4-flash"]["cacheReadInputTokens"], 480)
        self.assertEqual(metrics.total_input_tokens, 680)
        self.assertEqual(metrics.cache_hit_input_tokens, 480)
        self.assertEqual(metrics.cache_creation_input_tokens, 80)
        self.assertEqual(metrics.cache_miss_input_tokens, 200)
        self.assertAlmostEqual(metrics.cache_hit_rate, 480 / 680)
        self.assertAlmostEqual(metrics.total_cost_usd, 0.0042)

    def test_trace_records_sdk_cache_usage(self):
        metrics = TraceMetrics(model_name="deepseek-v4-flash")
        response = AgentResponse(
            model_usage={
                "deepseek-v4-flash": {
                    "inputTokens": 1000,
                    "outputTokens": 250,
                    "cacheReadInputTokens": 700,
                    "cacheCreationInputTokens": 50,
                    "costUSD": 0.012,
                }
            },
            elapsed_seconds=1.5,
        )

        EvalOrchestrator._record_trace(metrics, "accuracy", response)

        # Claude SDK inputTokens is the uncached portion; cache read/write
        # buckets are additional input tokens.
        self.assertEqual(metrics.total_input_tokens, 1750)
        self.assertEqual(metrics.cache_hit_input_tokens, 700)
        self.assertEqual(metrics.cache_miss_input_tokens, 1050)
        self.assertEqual(metrics.cache_creation_input_tokens, 50)
        self.assertAlmostEqual(metrics.cache_hit_rate, 0.4)
        self.assertEqual(metrics.spans[0].cache_hit_input_tokens, 700)
        self.assertAlmostEqual(metrics.spans[0].cache_hit_rate, 0.4)
        self.assertAlmostEqual(metrics.total_cost_usd, 0.012)

    def test_trace_sums_costs_for_multiple_models(self):
        metrics = TraceMetrics(model_name="deepseek-v4-flash")
        response = AgentResponse(
            model_usage={
                "deepseek-v4-flash": {"inputTokens": 100, "outputTokens": 10, "costUSD": 0.01},
                "claude-3-7-sonnet": {"inputTokens": 200, "outputTokens": 20, "costUSD": 0.02},
            }
        )

        EvalOrchestrator._record_trace(metrics, "quality", response)

        self.assertAlmostEqual(metrics.total_cost_usd, 0.03)

    def test_trace_records_sdk_large_cache_usage_without_truncation(self):
        metrics = TraceMetrics(model_name="deepseek-v4-flash")
        response = AgentResponse(
            model_usage={
                "deepseek-v4-flash": {
                    "inputTokens": 4435,
                    "outputTokens": 120,
                    "cacheReadInputTokens": 381849,
                    "cacheCreationInputTokens": 255569,
                }
            }
        )

        EvalOrchestrator._record_trace(metrics, "quality", response)

        self.assertEqual(metrics.total_input_tokens, 641853)
        self.assertEqual(metrics.cache_hit_input_tokens, 381849)
        self.assertEqual(metrics.cache_miss_input_tokens, 260004)
        self.assertEqual(metrics.cache_creation_input_tokens, 255569)
        self.assertAlmostEqual(metrics.cache_hit_rate, 381849 / 641853)

    def test_trace_records_deepseek_cache_usage_fields(self):
        metrics = TraceMetrics(model_name="deepseek-v4-flash")
        response = AgentResponse(
            model_usage={
                "__reported__": {
                    "prompt_tokens": 500,
                    "completion_tokens": 100,
                    "prompt_cache_hit_tokens": 400,
                    "prompt_cache_miss_tokens": 100,
                }
            }
        )

        EvalOrchestrator._record_trace(metrics, "quality", response)

        self.assertEqual(metrics.total_input_tokens, 500)
        self.assertEqual(metrics.total_output_tokens, 100)
        self.assertEqual(metrics.cache_hit_input_tokens, 400)
        self.assertEqual(metrics.cache_miss_input_tokens, 100)
        self.assertAlmostEqual(metrics.cache_hit_rate, 0.8)
        self.assertGreater(metrics.total_cost_usd, 0.0)

    def test_trace_metrics_backward_compatible(self):
        metrics = TraceMetrics.model_validate({
            "model_name": "deepseek-v4-flash",
            "total_input_tokens": 100,
            "total_output_tokens": 20,
            "total_tokens": 120,
            "total_cost_usd": 0.01,
            "spans": [{"name": "runtime", "input_tokens": 100, "output_tokens": 20}],
        })

        self.assertEqual(metrics.cache_hit_input_tokens, 0)
        self.assertIsNone(metrics.cache_hit_rate)

    def test_report_generation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = os.path.join(tmpdir, "output.md")
            html_path = os.path.join(tmpdir, "output_viz.html")

            summary1 = CaseEvalSummary(
                case_id="case_01",
                task_type="generation",
                total_elapsed_seconds=45.2,
                run_result=RunResult(status="success"),
                quality_result=QualityResult(
                    status="success",
                    overall_score=92.0,
                    strengths=["High modularity"],
                    weaknesses=["Missing docstrings"]
                ),
                overall_verdict="PASS"
            )

            ReportGenerator.generate_markdown_summary([summary1], md_path)
            ReportGenerator.generate_html_dashboard([summary1], html_path)

            self.assertTrue(os.path.exists(md_path))
            self.assertTrue(os.path.exists(html_path))

            with open(md_path, "r", encoding="utf-8") as f:
                md_content = f.read()
                self.assertIn("case_01", md_content)
                self.assertIn("PASS", md_content)
                self.assertIn("High modularity", md_content)
                self.assertIn("Tokens", md_content)
                self.assertIn("Cache Hit", md_content)
                self.assertIn("Cost (USD)", md_content)


if __name__ == "__main__":
    unittest.main()
