"""
server.py — Human-in-the-Loop (HITL) Interactive Web Console, Model Arena & Review Server using FastAPI.
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import HTMLResponse, JSONResponse

try:
    from .models import (
        CaseEvalSummary, RunResult, AccuracyResult, QualityResult,
        CsvDiffResult, HumanCalibrationRequest, HumanReviewEntry,
        PatchVerificationResult, RepairAuthorizationRequest, TraceMetrics
    )
    from .storage import AtomicJsonStorage
    from .sandbox import create_sandbox
    from .orchestrator import EvalOrchestrator
    from .cli import load_yaml_config
except (ImportError, ValueError):
    from models import (
        CaseEvalSummary, RunResult, AccuracyResult, QualityResult,
        CsvDiffResult, HumanCalibrationRequest, HumanReviewEntry,
        PatchVerificationResult, RepairAuthorizationRequest, TraceMetrics
    )
    from storage import AtomicJsonStorage
    from sandbox import create_sandbox
    from orchestrator import EvalOrchestrator
    from cli import load_yaml_config

logger = logging.getLogger("eval-server")

app = FastAPI(
    title="Eval-Agent HITL Review & Model Arena Console",
    description="Human-in-the-loop Active Calibration, Model Arena & Observability Console"
)

WORK_DIR = Path(os.getcwd())
DATASET_EXPORT_FILE = WORK_DIR / "eval" / "expert_dataset.jsonl"


def _quality_pillars(quality: Optional[dict]) -> dict:
    """Aggregate quality dimensions into the four engineering pillars."""
    buckets = {
        "architecture": [],
        "robustness": [],
        "security": [],
        "deliverability": [],
    }
    for dimension in (quality or {}).get("dimensions") or []:
        if not isinstance(dimension, dict):
            continue
        name = str(dimension.get("name") or dimension.get("dimension") or "").lower()
        try:
            score = float(dimension.get("score"))
        except (TypeError, ValueError):
            continue
        if any(term in name for term in ("架构", "规范", "模块", "architecture", "modular")):
            buckets["architecture"].append(score)
        elif any(term in name for term in ("健壮", "韧性", "异常", "稳定", "robust", "resilien")):
            buckets["robustness"].append(score)
        elif any(term in name for term in ("性能", "安全", "performance", "security")):
            buckets["security"].append(score)
        elif any(term in name for term in ("交付", "可观测", "运维", "体验", "deliver", "observ")):
            buckets["deliverability"].append(score)
    return {
        key: round(sum(values) / len(values), 2) if values else None
        for key, values in buckets.items()
    }


def get_arena_benchmark_data() -> dict:
    """Return metrics aggregated from persisted evaluation cases."""
    cases = get_all_cases()
    grouped: dict[str, list[dict]] = {}
    for case in cases:
        model_name = (case.get("trace") or {}).get("model_name") or "unknown"
        if model_name == "unknown":
            continue
        grouped.setdefault(model_name, []).append(case)

    models = []
    for model_name, model_cases in grouped.items():
        acc_scores = [
            case["accuracy"]["overall_score"] for case in model_cases
            if case.get("accuracy") and case["accuracy"].get("status") == "success"
        ]
        quality_scores = [
            case["quality"]["overall_score"] for case in model_cases
            if case.get("quality") and case["quality"].get("status") == "success"
        ]
        scores = acc_scores + quality_scores
        runs = [case["run"] for case in model_cases if case.get("run")]
        patches = [case["patch"] for case in model_cases if case.get("patch")]
        traces = [case["trace"] for case in model_cases if case.get("trace")]
        pillar_values = {key: [] for key in ("architecture", "robustness", "security", "deliverability")}
        for case in model_cases:
            for key, value in _quality_pillars(case.get("quality")).items():
                if value is not None:
                    pillar_values[key].append(value)
        pillars = {
            key: round(sum(values) / len(values), 2) if values else None
            for key, values in pillar_values.items()
        }
        overall = round(sum(scores) / len(scores), 2) if scores else None
        models.append({
            "name": model_name,
            "tag": "当前评测结果",
            "overall_grade": max(1, min(5, int(overall // 20))) if overall is not None else None,
            "overall_score": overall,
            "accuracy_score": round(sum(acc_scores) / len(acc_scores), 2) if acc_scores else None,
            "quality_score": round(sum(quality_scores) / len(quality_scores), 2) if quality_scores else None,
            "pillars": pillars,
            "sandbox_pass_rate": f"{sum(r.get('status') == 'success' for r in runs) / len(runs) * 100:.1f}%" if runs else "N/A",
            "healing_success_rate": f"{sum(p.get('run_after_patch_passed') is True for p in patches) / len(patches) * 100:.1f}%" if patches else "N/A",
            "avg_latency": f"{sum(t.get('total_elapsed_seconds', 0.0) for t in traces) / len(traces):.1f}s" if traces else "N/A",
            "avg_cost_usd": round(sum(t.get('total_cost_usd', 0.0) for t in traces) / len(traces), 6) if traces else None,
            "roi_index": None,
            "recommendation": f"基于 {len(model_cases)} 个已持久化用例的真实评测结果。",
            "case_count": len(model_cases),
        })
    models.sort(key=lambda item: item["overall_score"] or 0.0, reverse=True)
    efficiencies = [
        model["overall_score"] / model["avg_cost_usd"]
        for model in models
        if model["overall_score"] is not None
        and model["avg_cost_usd"] is not None
        and model["avg_cost_usd"] > 0
    ]
    max_efficiency = max(efficiencies, default=0.0)
    for rank, model in enumerate(models, start=1):
        model["rank"] = rank
        if (
            model["overall_score"] is not None
            and model["avg_cost_usd"] is not None
            and model["avg_cost_usd"] > 0
            and max_efficiency > 0
        ):
            model["roi_index"] = round(
                model["overall_score"] / model["avg_cost_usd"] / max_efficiency * 100
            )
    return {"benchmark_dataset_size": len(cases), "models": models}


def _create_configured_sandbox(config: dict):
    """Create the configured isolated sandbox using only supported provider options."""
    sandbox_config = config.get("sandbox", {})
    sandbox_type = sandbox_config.get("type", "utm")
    if sandbox_type == "utm":
        settings = sandbox_config.get("utm", {})
        sandbox_kwargs = {
            key: settings[key]
            for key in ("host", "port", "user", "ssh_key_path")
            if key in settings and settings[key] is not None
        }
    elif sandbox_type == "orbstack":
        settings = sandbox_config.get("orbstack", {})
        sandbox_kwargs = {
            key: settings[key]
            for key in ("machine_name",)
            if key in settings and settings[key] is not None
        }
    else:
        sandbox_kwargs = {}
    return create_sandbox(sandbox_type, **sandbox_kwargs)


def _legacy_demo_arena_data() -> dict:
    """Returns standardized cross-model benchmark data across the 4 engineering pillars and costs."""
    return {
        "benchmark_dataset_size": 100,
        "models": [
            {
                "rank": 1,
                "name": "Claude 3.7 Sonnet",
                "tag": "👑 架构与深度推理王者",
                "overall_grade": 5,
                "overall_score": 92.4,
                "accuracy_score": 94.0,
                "quality_score": 90.8,
                "pillars": {
                    "architecture": 95.0,
                    "robustness": 92.0,
                    "security": 93.0,
                    "deliverability": 83.0
                },
                "sandbox_pass_rate": "88.5%",
                "healing_success_rate": "92.0%",
                "avg_latency": "14.2s",
                "avg_cost_usd": 0.0245,
                "roi_index": 86,
                "recommendation": "极适合企业核心复杂业务重构、金融级安全审查与高难度架构设计。"
            },
            {
                "rank": 2,
                "name": "DeepSeek-V3",
                "tag": "⚡ 极致性价比之王 (95%成本降幅)",
                "overall_grade": 4,
                "overall_score": 88.6,
                "accuracy_score": 90.0,
                "quality_score": 87.2,
                "pillars": {
                    "architecture": 88.0,
                    "robustness": 86.0,
                    "security": 89.0,
                    "deliverability": 85.0
                },
                "sandbox_pass_rate": "84.0%",
                "healing_success_rate": "87.5%",
                "avg_latency": "9.8s",
                "avg_cost_usd": 0.0011,
                "roi_index": 99,
                "recommendation": "代码质量达到 SOTA 的 96%，但单 Case 成本仅为其 1/22，为大规模日常 CI/CD 门禁第一选择！"
            },
            {
                "rank": 3,
                "name": "GPT-4o",
                "tag": "🌐 综合均衡通用基准",
                "overall_grade": 4,
                "overall_score": 89.0,
                "accuracy_score": 89.5,
                "quality_score": 88.5,
                "pillars": {
                    "architecture": 90.0,
                    "robustness": 87.0,
                    "security": 91.0,
                    "deliverability": 86.0
                },
                "sandbox_pass_rate": "85.0%",
                "healing_success_rate": "88.0%",
                "avg_latency": "12.5s",
                "avg_cost_usd": 0.0180,
                "roi_index": 83,
                "recommendation": "多语言通用性良好，接口格式稳定性强。"
            },
            {
                "rank": 4,
                "name": "Qwen-2.5-Coder (72B)",
                "tag": "🛡️ 开源私有化部署标杆",
                "overall_grade": 4,
                "overall_score": 85.2,
                "accuracy_score": 86.5,
                "quality_score": 83.9,
                "pillars": {
                    "architecture": 85.0,
                    "robustness": 82.0,
                    "security": 84.0,
                    "deliverability": 84.5
                },
                "sandbox_pass_rate": "81.0%",
                "healing_success_rate": "83.0%",
                "avg_latency": "11.2s",
                "avg_cost_usd": 0.0018,
                "roi_index": 93,
                "recommendation": "适合完全物理隔离内网私有化算力部署的企业环境。"
            }
        ]
    }


def get_or_generate_trace(case_id: str, run_res, acc_res, qua_res) -> dict:
    """Loads trace_metrics.json or synthesizes realistic trace data."""
    trace_path = WORK_DIR / case_id / "trace_metrics.json"
    existing_trace = AtomicJsonStorage.load(str(trace_path), TraceMetrics)
    if existing_trace:
        return existing_trace.model_dump()

    # Old/partial cases have no trace file; expose only observed values and never fabricate usage.
    return TraceMetrics(
        model_name=os.getenv("EVAL_MODEL", "unknown"),
        total_elapsed_seconds=run_res.elapsed_seconds if run_res else 0.0,
        spans=[],
    ).model_dump()


def _is_case_pass(
    run_res: Optional[RunResult],
    acc_res: Optional[AccuracyResult],
    qua_res: Optional[QualityResult],
    diff_res: Optional[CsvDiffResult],
) -> bool:
    """Keep API verdicts aligned with the orchestrator's pass thresholds."""
    return bool(
        run_res
        and run_res.status == "success"
        and acc_res
        and acc_res.status == "success"
        and acc_res.overall_score >= 60.0
        and qua_res
        and qua_res.status == "success"
        and qua_res.overall_score >= 60.0
        and (
            not diff_res
            or (
                diff_res.status == "success"
                and diff_res.matched_ratio >= 0.8
            )
        )
    )


def get_all_cases() -> List[dict]:
    """Scans evaluation results from the workspace."""
    cases = []
    for p in sorted(WORK_DIR.iterdir()):
        if p.is_dir() and (p.name.isdigit() or p.name.startswith("case")):
            case_id = p.name
            run_res = AtomicJsonStorage.load(str(p / "eval_run_result.json"), RunResult)
            acc_res = AtomicJsonStorage.load(str(p / "eval_accuracy.json"), AccuracyResult)
            qua_res = AtomicJsonStorage.load(str(p / "eval_quality.json"), QualityResult)
            diff_res = AtomicJsonStorage.load(str(p / "eval_csv_diff.json"), CsvDiffResult)
            review_res = AtomicJsonStorage.load(str(p / "human_review.json"), HumanReviewEntry)
            patch_res = AtomicJsonStorage.load(str(p / "patch_result.json"), PatchVerificationResult)
            trace_data = get_or_generate_trace(case_id, run_res, acc_res, qua_res)

            cases.append({
                "case_id": case_id,
                "run": run_res.model_dump() if run_res else None,
                "accuracy": acc_res.model_dump() if acc_res else None,
                "quality": qua_res.model_dump() if qua_res else None,
                "diff": diff_res.model_dump() if diff_res else None,
                "patch": patch_res.model_dump() if patch_res else None,
                "human_review": review_res.model_dump() if review_res else None,
                "trace": trace_data,
                "overall_verdict": "PASS" if _is_case_pass(run_res, acc_res, qua_res, diff_res) else "FAIL"
            })
    return cases


@app.get("/api/arena")
async def get_arena():
    return get_arena_benchmark_data()


@app.get("/api/cases")
async def list_cases():
    return get_all_cases()


@app.get("/api/case/{case_id}")
async def get_case(case_id: str):
    case_dir = WORK_DIR / case_id
    if not case_dir.exists():
        raise HTTPException(status_code=404, detail="Case directory not found")

    run_res = AtomicJsonStorage.load(str(case_dir / "eval_run_result.json"), RunResult)
    acc_res = AtomicJsonStorage.load(str(case_dir / "eval_accuracy.json"), AccuracyResult)
    qua_res = AtomicJsonStorage.load(str(case_dir / "eval_quality.json"), QualityResult)
    diff_res = AtomicJsonStorage.load(str(case_dir / "eval_csv_diff.json"), CsvDiffResult)
    review_res = AtomicJsonStorage.load(str(case_dir / "human_review.json"), HumanReviewEntry)
    patch_res = AtomicJsonStorage.load(str(case_dir / "patch_result.json"), PatchVerificationResult)
    trace_data = get_or_generate_trace(case_id, run_res, acc_res, qua_res)

    return {
        "case_id": case_id,
        "run": run_res.model_dump() if run_res else None,
        "accuracy": acc_res.model_dump() if acc_res else None,
        "quality": qua_res.model_dump() if qua_res else None,
        "diff": diff_res.model_dump() if diff_res else None,
        "patch": patch_res.model_dump() if patch_res else None,
        "human_review": review_res.model_dump() if review_res else None,
        "trace": trace_data,
        "overall_verdict": "PASS" if _is_case_pass(run_res, acc_res, qua_res, diff_res) else "FAIL"
    }


@app.post("/api/case/{case_id}/calibrate")
async def calibrate_case(case_id: str, req: HumanCalibrationRequest):
    """Saves human expert review with Dual-Dimension (Accuracy & Quality) calibration and appends to DPO dataset."""
    case_dir = WORK_DIR / case_id
    if not case_dir.exists():
        raise HTTPException(status_code=404, detail="Case directory not found")

    acc_res = AtomicJsonStorage.load(str(case_dir / "eval_accuracy.json"), AccuracyResult)
    qua_res = AtomicJsonStorage.load(str(case_dir / "eval_quality.json"), QualityResult)

    orig_acc_grade = acc_res.overall_grade if acc_res else None
    orig_qua_grade = qua_res.overall_grade if qua_res else None
    orig_score = qua_res.overall_score if qua_res else 0.0
    orig_grade = qua_res.overall_grade if qua_res else 3

    calib_acc_grade = req.calibrated_accuracy_grade or orig_acc_grade or 4
    calib_qua_grade = req.calibrated_quality_grade or orig_qua_grade or 4
    calib_grade = req.calibrated_grade or min(calib_acc_grade, calib_qua_grade)
    calib_score = req.calibrated_score if req.calibrated_score is not None else (calib_grade * 20.0)

    entry = HumanReviewEntry(
        case_id=case_id,
        reviewer=req.reviewer,
        original_score=orig_score,
        calibrated_score=calib_score,
        original_grade=orig_grade,
        calibrated_grade=calib_grade,
        original_accuracy_grade=orig_acc_grade,
        calibrated_accuracy_grade=calib_acc_grade,
        original_quality_grade=orig_qua_grade,
        calibrated_quality_grade=calib_qua_grade,
        is_agreed_with_ai=req.is_agreed_with_ai,
        expert_feedback=req.expert_feedback
    )

    AtomicJsonStorage.save(str(case_dir / "human_review.json"), entry)

    DATASET_EXPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATASET_EXPORT_FILE, "a", encoding="utf-8") as f:
        export_payload = {
            "case_id": case_id,
            "ai_evaluation": {
                "accuracy": acc_res.model_dump() if acc_res else {},
                "quality": qua_res.model_dump() if qua_res else {}
            },
            "human_calibration": entry.model_dump(mode="json")
        }
        f.write(json.dumps(export_payload, ensure_ascii=False) + "\n")

    return {"status": "success", "message": f"Case {case_id} calibrated (Acc: G{calib_acc_grade}, Qua: G{calib_qua_grade}, Overall: G{calib_grade})."}


@app.post("/api/case/{case_id}/execute-repair")
async def execute_repair(case_id: str, req: RepairAuthorizationRequest):
    """Run the real repair agent after an explicit human approval."""
    case_dir = WORK_DIR / case_id
    if not case_dir.exists():
        raise HTTPException(status_code=404, detail="Case directory not found")

    if not req.authorized:
        raise HTTPException(status_code=403, detail="必须明确授权后才能执行代码修复。")
    human_review = AtomicJsonStorage.load(str(case_dir / "human_review.json"), HumanReviewEntry)
    if human_review is None:
        raise HTTPException(status_code=403, detail="请先完成人工复核，再授权代码修复。")
    human_guidance = req.human_guidance.strip()
    logger.info("[%s] Human-approved repair requested by %s", case_id, human_review.reviewer)

    summary = AtomicJsonStorage.load(
        str(case_dir / "case_summary.json"), CaseEvalSummary
    )
    if summary is None:
        raise HTTPException(
            status_code=409,
            detail="当前用例缺少 case_summary.json，无法安全构造修复上下文，请先完成一次评测。",
        )

    config = load_yaml_config(WORK_DIR / "eval_config.yaml")
    trace_model = (
        summary.trace_metrics.model_name
        if summary.trace_metrics and summary.trace_metrics.model_name != "unknown"
        else None
    )
    model_name = (
        trace_model
        or os.getenv("EVAL_MODEL")
        or os.getenv("MODEL")
        or config.get("llm", {}).get("default_model")
        or "deepseek-v4-flash"
    )
    orchestrator = EvalOrchestrator(
        work_dir=str(WORK_DIR),
        sandbox=_create_configured_sandbox(config),
        max_concurrency=1,
        enable_auto_repair=True,
        model_name=model_name,
    )
    patch_res = await orchestrator.execute_authorized_repair(
        case_id, summary, human_guidance=human_guidance
    )

    if not patch_res.patch_applied:
        repair_status = "not_applied"
    elif patch_res.run_after_patch_passed:
        repair_status = "success"
    else:
        repair_status = "verification_failed"

    return {
        "status": repair_status,
        "repair_executed": patch_res.patch_applied,
        "sandbox_passed": patch_res.run_after_patch_passed,
        "score_improved": patch_res.score_improved,
        "old_score": patch_res.old_score,
        "new_score": patch_res.new_score,
        "old_grade": round(patch_res.old_score / 20) if patch_res.old_score is not None else None,
        "new_grade": round(patch_res.new_score / 20) if patch_res.new_score is not None else None,
        "log": patch_res.verification_log,
        "human_guidance": human_guidance,
    }


@app.get("/", response_class=HTMLResponse)
async def serve_dashboard():
    """Renders the comprehensive, high-credibility 5-Tier Grade HITL interactive web console with Model Arena."""
    html = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Eval-Agent</title>
<style>
:root{--bg:#09090b;--bg-elev:#131316;--bg-hover:#1a1a1e;--bg-inset:#07070a;--text:#e4e4e7;--text-dim:#a1a1aa;--text-faint:#52525b;--accent:#3b82f6;--border:rgba(255,255,255,0.06);--border-mid:rgba(255,255,255,0.10);--pass:#22c55e;--fail:#ef4444;--warn:#f59e0b}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Inter","Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;flex-direction:column;-webkit-font-smoothing:antialiased}
code,pre,.mono{font-family:"SF Mono","JetBrains Mono",Consolas,monospace}

/* Layout */
.top-nav{height:52px;background:var(--bg-elev);border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;padding:0 20px;position:sticky;top:0;z-index:100}
.logo{display:flex;align-items:center;gap:8px;font-size:14px;font-weight:600}
.logo svg{width:16px;height:16px;color:var(--accent)}
.nav-right{display:flex;align-items:center;gap:12px}
.case-select{background:var(--bg-inset);border:1px solid var(--border);border-radius:6px;padding:5px 10px;color:var(--text);font-size:12px;cursor:pointer;outline:none}
.case-select:focus{border-color:var(--accent)}
.main{flex:1;overflow-y:auto;padding:20px;max-width:1200px;margin:0 auto;width:100%}

/* Grid */
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.grid-4{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
@media(max-width:768px){.grid-2{grid-template-columns:1fr}}

/* Cards */
.metric-card{background:var(--bg-elev);border:1px solid var(--border);border-radius:8px;padding:14px 16px}
.metric-label{font-size:11px;font-weight:600;color:var(--text-faint);text-transform:uppercase;letter-spacing:.03em}
.metric-value{font-size:22px;font-weight:700;margin-top:4px}
.metric-sub{font-size:11px;color:var(--text-faint);margin-top:2px}

.panel{background:var(--bg-elev);border:1px solid var(--border);border-radius:8px;margin-bottom:12px;overflow:hidden}
.panel-head{padding:12px 16px;border-bottom:1px solid var(--border);font-size:12px;font-weight:600;color:var(--text-dim);display:flex;align-items:center;justify-content:space-between}
.panel-body{padding:16px;font-size:13px;line-height:1.6;color:var(--text)}

/* Badges */
.badge{display:inline-flex;align-items:center;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;letter-spacing:.02em}
.badge-pass{background:rgba(34,197,94,0.12);color:var(--pass)}
.badge-fail{background:rgba(239,68,68,0.12);color:var(--fail)}
.badge-grade{background:var(--bg-inset);color:var(--text-dim);border:1px solid var(--border)}
.badge-warn{background:rgba(245,158,11,0.12);color:var(--warn)}

/* Score bar */
.score-row{display:flex;align-items:center;gap:12px;margin-bottom:8px}
.score-label{font-size:12px;color:var(--text-faint);width:120px;flex-shrink:0}
.score-bar{flex:1;height:6px;background:var(--bg-inset);border-radius:3px;overflow:hidden}
.score-fill{height:100%;border-radius:3px;transition:width .3s}
.score-val{font-size:12px;font-weight:600;width:40px;text-align:right;flex-shrink:0}

/* Dim table */
.dim-table{width:100%;border-collapse:collapse;font-size:12px}
.dim-table th{text-align:left;padding:8px 12px;border-bottom:1px solid var(--border);font-size:11px;font-weight:600;color:var(--text-faint);text-transform:uppercase}
.dim-table td{padding:8px 12px;border-bottom:1px solid var(--border);vertical-align:top}
.dim-table tr:last-child td{border-bottom:none}

/* Tag list */
.tag-list{list-style:none}
.tag-list li{padding:8px 12px;background:var(--bg-inset);border-radius:6px;margin-bottom:6px;font-size:12px;border-left:3px solid var(--border-mid);line-height:1.5}
.tag-list.weakness li{border-left-color:var(--fail)}
.tag-list.suggestion li{border-left-color:var(--accent)}
.tag-list.strength li{border-left-color:var(--pass)}

/* Terminal */
.terminal{background:#000;border:1px solid var(--border);border-radius:6px;padding:14px;font-family:"SF Mono",Consolas,monospace;font-size:12px;color:#a1a1aa;overflow-x:auto;line-height:1.6;max-height:300px;overflow-y:auto;white-space:pre-wrap}

/* Trace waterfall */
.trace-table{width:100%;border-collapse:collapse;font-size:12px}
.trace-table th{text-align:left;padding:8px 12px;border-bottom:1px solid var(--border);font-size:11px;font-weight:600;color:var(--text-faint)}
.trace-table td{padding:8px 12px;border-bottom:1px solid var(--border);vertical-align:top}
.latency-bar-bg{background:var(--bg-inset);height:5px;border-radius:3px;overflow:hidden;margin-top:4px}
.latency-bar-fill{height:100%;background:var(--accent);border-radius:3px}

/* Forms */
.form-group{margin-bottom:12px}
.form-label{display:block;font-size:12px;color:var(--text-faint);margin-bottom:4px}
.form-input,.form-select,.form-textarea{width:100%;background:var(--bg-inset);border:1px solid var(--border);border-radius:6px;padding:8px 10px;color:var(--text);font-size:12px;outline:none}
.form-input:focus,.form-select:focus,.form-textarea:focus{border-color:var(--accent)}
.form-textarea{min-height:60px;resize:vertical;font-family:inherit}
.form-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:8px}
.btn{display:inline-flex;align-items:center;gap:5px;padding:7px 14px;border-radius:6px;font-weight:600;font-size:12px;cursor:pointer;border:none;transition:all .15s}
.btn-primary{background:var(--accent);color:#fff}
.btn-primary:hover{opacity:.9}
.btn-ghost{background:var(--bg-hover);color:var(--text-dim);border:1px solid var(--border)}
.btn-ghost:hover{color:var(--text)}
.btn:disabled{opacity:.5;cursor:not-allowed}

/* Modal */
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,0.6);display:none;align-items:center;justify-content:center;z-index:200}
.modal-overlay.active{display:flex}
.modal{background:var(--bg-elev);border:1px solid var(--border-mid);border-radius:10px;width:90%;max-width:560px;max-height:80vh;overflow-y:auto}
.modal-head{padding:16px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.modal-title{font-size:14px;font-weight:600}
.modal-close{background:none;border:none;color:var(--text-faint);cursor:pointer;font-size:18px;padding:4px}
.modal-close:hover{color:var(--text)}
.modal-body{padding:20px}

/* Misc */
.spinner{width:24px;height:24px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .6s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.loading{display:flex;align-items:center;justify-content:center;padding:40px;gap:10px;color:var(--text-faint);font-size:13px}
.empty{text-align:center;padding:40px;color:var(--text-faint);font-size:13px}
.toast{position:fixed;bottom:20px;right:20px;padding:10px 16px;border-radius:6px;font-size:13px;font-weight:500;z-index:300;opacity:0;transition:opacity .2s;pointer-events:none}
.toast.show{opacity:1}
.toast-success{background:var(--bg-elev);border:1px solid var(--border-mid);color:var(--text)}
.toast-error{background:var(--bg-elev);border:1px solid var(--fail);color:var(--fail)}
.divider{height:1px;background:var(--border);margin:16px 0}
.section-gap{margin-bottom:20px}
.pre-scroll{background:var(--bg-inset);border:1px solid var(--border);border-radius:6px;padding:12px;overflow-x:auto;font-size:12px;line-height:1.5}
</style>
</head>
<body>

<div class="top-nav">
    <div class="logo">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
        Eval-Agent
    </div>
    <div class="nav-right">
        <select class="case-select" id="case-select" onchange="loadCase(this.value)"><option value="">Select case...</option></select>
    </div>
</div>

<div class="main" id="main-content">
    <div class="loading"><div class="spinner"></div>Loading...</div>
</div>

<!-- Calibrate Modal -->
<div class="modal-overlay" id="calibrate-modal">
    <div class="modal">
        <div class="modal-head">
            <span class="modal-title">Expert Calibration (双维度人机校准)</span>
            <button class="modal-close" onclick="closeModal('calibrate-modal')">&times;</button>
        </div>
        <div class="modal-body">
            <div class="grid-2" style="margin-bottom:12px">
                <div class="form-group">
                    <label class="form-label">Accuracy 校准 (功能准确性)</label>
                    <select class="form-select" id="cal-acc-grade" onchange="autoSyncOverallGrade()">
                        <option value="5">A / G5 (100分 - 卓越)</option>
                        <option value="4" selected>B / G4 (80分 - 良好)</option>
                        <option value="3">C / G3 (60分 - 合格)</option>
                        <option value="2">D / G2 (40分 - 较差)</option>
                        <option value="1">F / G1 (20分 - 失败)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">Quality 校准 (工程质量)</label>
                    <select class="form-select" id="cal-qua-grade" onchange="autoSyncOverallGrade()">
                        <option value="5">A / G5 (100分 - 卓越)</option>
                        <option value="4" selected>B / G4 (80分 - 良好)</option>
                        <option value="3">C / G3 (60分 - 合格)</option>
                        <option value="2">D / G2 (40分 - 较差)</option>
                        <option value="1">F / G1 (20分 - 失败)</option>
                    </select>
                </div>
            </div>
            <div class="form-group">
                <label class="form-label">Overall 最终综合定级 (Final Verdict Grade)</label>
                <select class="form-select" id="cal-overall-grade">
                    <option value="5">A / G5 (100分 - 卓越)</option>
                    <option value="4" selected>B / G4 (80分 - 良好)</option>
                    <option value="3">C / G3 (60分 - 合格)</option>
                    <option value="2">D / G2 (40分 - 较差)</option>
                    <option value="1">F / G1 (20分 - 失败)</option>
                </select>
            </div>
            <div class="form-group">
                <label class="form-label">是否认同 AI 判定？</label>
                <select class="form-select" id="cal-agree">
                    <option value="true">认同 AI 判定 (Agreed)</option>
                    <option value="false">存在误判 / 遗漏 / 过于严苛 (Disagreed)</option>
                </select>
            </div>
            <div class="form-group">
                <label class="form-label">专家纠偏归因与复核说明 (将导出沉淀入 DPO 对齐数据集)</label>
                <textarea class="form-textarea" id="cal-feedback" placeholder="例如：该边界在框架全局拦截器中已兜底，不属于业务缺陷，将 Accuracy 上调为 Grade 4..."></textarea>
            </div>
            <div class="form-group">
                <label class="form-label">评审专家</label>
                <input class="form-input" id="cal-reviewer" value="expert_engineer" />
            </div>
            <div class="form-actions">
                <button class="btn btn-ghost" onclick="closeModal('calibrate-modal')">Cancel</button>
                <button class="btn btn-primary" id="cal-submit" onclick="submitCalibration()">Save Calibration</button>
            </div>
        </div>
    </div>
</div>

<!-- Repair Modal -->
<div class="modal-overlay" id="repair-modal">
    <div class="modal">
        <div class="modal-head">
            <span class="modal-title">Authorize AI Repair</span>
            <button class="modal-close" onclick="closeModal('repair-modal')">&times;</button>
        </div>
        <div class="modal-body">
            <div class="form-group">
                <label class="form-label">Human guidance (optional)</label>
                <textarea class="form-textarea" id="repair-guidance" placeholder="Additional instructions for the repair agent..."></textarea>
            </div>
            <div class="form-actions">
                <button class="btn btn-ghost" onclick="closeModal('repair-modal')">Cancel</button>
                <button class="btn btn-primary" id="repair-submit" onclick="submitRepair()">Execute</button>
            </div>
        </div>
    </div>
</div>

<div class="toast" id="toast"></div>

<script>
let currentCaseId = null;
let currentCaseData = null;
let casesData = [];

async function fetchJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(res.statusText);
    return res.json();
}

function badge(verdict) {
    const cls = verdict === 'PASS' ? 'badge-pass' : 'badge-fail';
    return '<span class="badge ' + cls + '">' + verdict + '</span>';
}

function gradeBadge(grade) {
    if (!grade) return '';
    const map = { 5: 'A (G5)', 4: 'B (G4)', 3: 'C (G3)', 2: 'D (G2)', 1: 'F (G1)' };
    const label = map[grade] || ('G' + grade);
    return '<span class="badge badge-grade">' + label + '</span>';
}

function scoreColor(score) {
    if (score >= 80) return '#22c55e';
    if (score >= 60) return '#a1a1aa';
    return '#ef4444';
}

function escapeHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function showToast(msg, type) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className = 'toast show toast-' + (type || 'success');
    setTimeout(() => t.classList.remove('show'), 3000);
}

function openModal(id) { document.getElementById(id).classList.add('active'); }
function closeModal(id) { document.getElementById(id).classList.remove('active'); }

// Init: load case list
async function init() {
    try {
        casesData = await fetchJSON('/api/cases');
        const sel = document.getElementById('case-select');
        sel.innerHTML = casesData.map(c => '<option value="' + c.case_id + '">' + c.case_id + '</option>').join('');
        if (casesData.length > 0) loadCase(casesData[0].case_id);
    } catch(e) {
        document.getElementById('main-content').innerHTML = '<div class="empty">Error: ' + e.message + '</div>';
    }
}

// Load case detail
async function loadCase(caseId) {
    if (!caseId) return;
    currentCaseId = caseId;
    document.getElementById('case-select').value = caseId;
    const el = document.getElementById('main-content');
    el.innerHTML = '<div class="loading"><div class="spinner"></div>Loading ' + caseId + '...</div>';
    try {
        const c = await fetchJSON('/api/case/' + caseId);
        currentCaseData = c;
        el.innerHTML = renderCase(c);
    } catch(e) {
        el.innerHTML = '<div class="empty">Error: ' + e.message + '</div>';
    }
}

function renderCase(c) {
    let html = '';

    // === Top metrics ===
    const accScore = c.accuracy ? c.accuracy.overall_score : null;
    const quaScore = c.quality ? c.quality.overall_score : null;
    const accGrade = c.accuracy ? c.accuracy.overall_grade : null;
    const quaGrade = c.quality ? c.quality.overall_grade : null;
    const trace = c.trace || {};

    html += '<div class="grid-4 section-gap">';
    html += metricCard('Verdict', badge(c.overall_verdict), c.human_review ? ('Review: ' + gradeBadge(c.human_review.calibrated_grade)) : '');
    html += metricCard('Accuracy', accScore !== null ? accScore.toFixed(0) : 'N/A', accGrade ? gradeBadge(accGrade) : '');
    html += metricCard('Quality', quaScore !== null ? quaScore.toFixed(0) : 'N/A', quaGrade ? gradeBadge(quaGrade) : '');
    html += metricCard('Sandbox', c.run ? c.run.status.toUpperCase() : 'N/A', c.run ? c.run.elapsed_seconds.toFixed(1) + 's' : '');
    html += '</div>';

    // === Accuracy panel ===
    if (c.accuracy) {
        html += '<div class="panel"><div class="panel-head">Accuracy Analysis' + (accGrade ? ' &nbsp; ' + gradeBadge(accGrade) : '') + '</div><div class="panel-body">';

        // Dimensions table
        if (c.accuracy.dimensions && c.accuracy.dimensions.length > 0) {
            html += '<table class="dim-table"><thead><tr><th>Dimension</th><th>Grade</th><th style="width:50px">Score</th><th>Reason</th></tr></thead><tbody>';
            c.accuracy.dimensions.forEach(d => {
                html += '<tr><td><b>' + escapeHtml(d.dimension || d.name || '') + '</b></td>';
                html += '<td>' + gradeBadge(d.grade) + '</td>';
                html += '<td>' + (d.score !== undefined ? d.score.toFixed(0) : '-') + '</td>';
                html += '<td style="color:var(--text-dim)">' + escapeHtml(d.reason || d.comment || '--') + '</td></tr>';
            });
            html += '</tbody></table>';
        }

        // Score bar
        if (accScore !== null) {
            html += '<div class="divider"></div>';
            html += scoreBarRow('Overall Accuracy', accScore);
        }

        // Strengths / Weaknesses / Suggestions
        html += renderTagList('Strengths', c.accuracy.strengths, 'strength');
        html += renderTagList('Weaknesses', c.accuracy.weaknesses, 'weakness');
        html += renderTagList('Repair Suggestions', c.accuracy.repair_suggestions, 'suggestion');

        html += '</div></div>';
    }

    // === Quality panel ===
    if (c.quality) {
        html += '<div class="panel"><div class="panel-head">Engineering Quality' + (quaGrade ? ' &nbsp; ' + gradeBadge(quaGrade) : '') + '</div><div class="panel-body">';

        // Dimensions table
        if (c.quality.dimensions && c.quality.dimensions.length > 0) {
            html += '<table class="dim-table"><thead><tr><th>Pillar</th><th>Grade</th><th style="width:50px">Score</th><th>Comment</th></tr></thead><tbody>';
            c.quality.dimensions.forEach(d => {
                html += '<tr><td><b>' + escapeHtml(d.name || d.dimension || '') + '</b></td>';
                html += '<td>' + gradeBadge(d.grade) + '</td>';
                html += '<td>' + (d.score !== undefined ? d.score.toFixed(0) : '-') + '</td>';
                html += '<td style="color:var(--text-dim)">' + escapeHtml(d.comment || d.reason || '--') + '</td></tr>';
            });
            html += '</tbody></table>';
        }

        // Score bars
        if (quaScore !== null) {
            html += '<div class="divider"></div>';
            html += scoreBarRow('Overall', quaScore);
        }

        html += renderTagList('Strengths', c.quality.strengths, 'strength');
        html += renderTagList('Weaknesses', c.quality.weaknesses, 'weakness');
        html += renderTagList('Engineering Suggestions', c.quality.repair_suggestions, 'suggestion');

        html += '</div></div>';
    }

    // === Sandbox panel ===
    if (c.run) {
        html += '<div class="panel"><div class="panel-head">Sandbox Execution</div><div class="panel-body">';
        html += '<div class="grid-2" style="margin-bottom:12px">';
        html += '<div><span style="color:var(--text-faint);font-size:12px">Method:</span> ' + escapeHtml(c.run.run_method || 'N/A') + '</div>';
        html += '<div><span style="color:var(--text-faint);font-size:12px">Elapsed:</span> ' + (c.run.elapsed_seconds || 0).toFixed(1) + 's</div>';
        html += '<div><span style="color:var(--text-faint);font-size:12px">Exit code:</span> ' + (c.run.exit_code !== undefined ? c.run.exit_code : 'N/A') + '</div>';
        html += '<div><span style="color:var(--text-faint);font-size:12px">Attempts:</span> ' + (c.run.attempt_count || 1) + '</div>';
        html += '</div>';
        if (c.run.log_summary || c.run.error_snippet || c.run.note) {
            html += '<div class="terminal">' + escapeHtml(c.run.error_snippet || c.run.log_summary || c.run.note) + '</div>';
        }
        html += '</div></div>';
    }

    // === CSV Diff panel ===
    if (c.diff) {
        html += '<div class="panel"><div class="panel-head">CSV Diff</div><div class="panel-body">';
        const ratio = c.diff.matched_ratio !== undefined ? (c.diff.matched_ratio * 100).toFixed(1) : 'N/A';
        html += '<div style="margin-bottom:8px"><span style="color:var(--text-faint);font-size:12px">Matched:</span> <b>' + ratio + '%</b></div>';
        html += '<div style="margin-bottom:8px"><span style="color:var(--text-faint);font-size:12px">Status:</span> ' + escapeHtml(c.diff.status || 'N/A') + '</div>';
        if (c.diff.details) {
            html += '<pre class="pre-scroll">' + escapeHtml(JSON.stringify(c.diff.details, null, 2)) + '</pre>';
        }
        html += '</div></div>';
    }

    // === Trace & Cost panel ===
    if (trace && (trace.total_tokens > 0 || trace.total_elapsed_seconds > 0 || (trace.spans && trace.spans.length > 0))) {
        html += '<div class="panel"><div class="panel-head">Observability &amp; Trace</div><div class="panel-body">';

        // Cost & token metrics
        html += '<div class="grid-4" style="margin-bottom:12px">';
        html += metricCard('Cost', trace.total_cost_usd ? '$' + trace.total_cost_usd.toFixed(5) : '$0', trace.total_cost_usd ? (trace.total_cost_usd * 7.25).toFixed(2) + ' RMB' : '');
        html += metricCard('Tokens', (trace.total_tokens || 0).toLocaleString(), 'In: ' + (trace.total_input_tokens || 0) + ' / Out: ' + (trace.total_output_tokens || 0));
        const cacheRate = trace.cache_hit_rate != null ? (trace.cache_hit_rate * 100).toFixed(1) + '%' : 'N/A';
        html += metricCard('Cache Hit', cacheRate, 'Hit: ' + (trace.cache_hit_input_tokens || 0).toLocaleString());
        html += metricCard('Latency', (trace.total_elapsed_seconds || 0).toFixed(1) + 's', trace.model_name || 'unknown');
        html += '</div>';

        // Trace waterfall
        if (trace.spans && trace.spans.length > 0) {
            const maxElapsed = Math.max(...trace.spans.map(s => s.elapsed_seconds || 0.001), 0.001);
            html += '<table class="trace-table"><thead><tr><th>Span</th><th>Latency</th><th>Tokens (In/Out)</th><th>Cost</th><th>Status</th></tr></thead><tbody>';
            trace.spans.forEach(s => {
                const widthPct = Math.max(5, Math.min(100, ((s.elapsed_seconds || 0) / maxElapsed) * 100));
                html += '<tr>';
                html += '<td><b>' + escapeHtml(s.name || '') + '</b></td>';
                html += '<td><div>' + (s.elapsed_seconds || 0).toFixed(1) + 's</div><div class="latency-bar-bg"><div class="latency-bar-fill" style="width:' + widthPct + '%"></div></div></td>';
                html += '<td>' + (s.total_tokens > 0 ? s.total_tokens + ' <span style="color:var(--text-faint)">(' + s.input_tokens + '/' + s.output_tokens + ')</span>' : '<span style="color:var(--text-faint)">0</span>') + '</td>';
                html += '<td>' + (s.cost_usd > 0 ? '$' + s.cost_usd.toFixed(5) : '$0') + '</td>';
                const sc = s.status === 'success' ? 'var(--pass)' : 'var(--fail)';
                html += '<td><span style="color:' + sc + ';font-size:11px;font-weight:600">' + escapeHtml((s.status || '').toUpperCase()) + '</span>';
                if (s.details) html += '<div style="color:var(--text-faint);font-size:11px;margin-top:2px">' + escapeHtml(s.details) + '</div>';
                html += '</td></tr>';
            });
            html += '</tbody></table>';
        }

        html += '</div></div>';
    }

    // === Patch / Repair result ===
    if (c.patch) {
        html += '<div class="panel"><div class="panel-head">AI Repair Result</div><div class="panel-body">';
        html += '<div class="grid-2">';
        html += '<div><span style="color:var(--text-faint);font-size:12px">Patch applied:</span> ' + (c.patch.patch_applied ? '<span class="badge badge-pass">Yes</span>' : '<span class="badge badge-fail">No</span>') + '</div>';
        html += '<div><span style="color:var(--text-faint);font-size:12px">Verification:</span> ' + (c.patch.run_after_patch_passed ? '<span class="badge badge-pass">Passed</span>' : '<span class="badge badge-fail">Failed</span>') + '</div>';
        if (c.patch.score_improved !== undefined) {
            html += '<div><span style="color:var(--text-faint);font-size:12px">Score:</span> ' + (c.patch.old_score || 0).toFixed(0) + ' -> ' + (c.patch.new_score || 0).toFixed(0) + (c.patch.score_improved ? ' <span class="badge badge-pass">Improved</span>' : '') + '</div>';
            html += '<div><span style="color:var(--text-faint);font-size:12px">Grade:</span> G' + (c.patch.old_grade || '-') + ' -> G' + (c.patch.new_grade || '-') + '</div>';
        }
        html += '</div>';
        if (c.patch.verification_log) {
            html += '<div class="terminal" style="margin-top:12px">' + escapeHtml(c.patch.verification_log) + '</div>';
        }
        html += '</div></div>';
    }

    // === HITL Actions ===
    html += '<div class="panel"><div class="panel-head">Human-in-the-Loop</div><div class="panel-body">';

    // Show existing review
    if (c.human_review) {
        const hr = c.human_review;
        html += '<div style="background:var(--bg-inset);border:1px solid var(--border);border-radius:6px;padding:12px;margin-bottom:14px">';
        html += '<div style="display:flex;flex-wrap:wrap;gap:16px;align-items:center;margin-bottom:8px">';
        html += '<div><span style="color:var(--text-faint);font-size:12px">评审专家:</span> <b>' + escapeHtml(hr.reviewer || 'expert') + '</b></div>';
        if (hr.calibrated_accuracy_grade) {
            html += '<div><span style="color:var(--text-faint);font-size:12px">Accuracy:</span> ' + gradeBadge(hr.calibrated_accuracy_grade) + '</div>';
        }
        if (hr.calibrated_quality_grade) {
            html += '<div><span style="color:var(--text-faint);font-size:12px">Quality:</span> ' + gradeBadge(hr.calibrated_quality_grade) + '</div>';
        }
        html += '<div><span style="color:var(--text-faint);font-size:12px">最终裁决:</span> ' + gradeBadge(hr.calibrated_grade) + '</div>';
        html += '<div><span style="color:var(--text-faint);font-size:12px">认同AI:</span> ' + (hr.is_agreed_with_ai ? '<span class="badge badge-pass">Agreed</span>' : '<span class="badge badge-fail">Disagreed</span>') + '</div>';
        html += '</div>';
        if (hr.expert_feedback) {
            html += '<div style="font-size:12px;color:var(--text-dim);line-height:1.5;border-top:1px solid var(--border);padding-top:8px"><span style="color:var(--text-faint)">专家说明:</span> ' + escapeHtml(hr.expert_feedback) + '</div>';
        }
        html += '</div>';
    }

    // Combined repair suggestions
    const allSuggs = [
        ...(c.accuracy && c.accuracy.repair_suggestions ? c.accuracy.repair_suggestions : []),
        ...(c.quality && c.quality.repair_suggestions ? c.quality.repair_suggestions : [])
    ];
    if (allSuggs.length > 0) {
        html += '<div style="margin-bottom:12px"><div style="font-size:12px;color:var(--text-faint);margin-bottom:6px">AI Proposed Repair Strategy:</div>';
        html += '<ul class="tag-list suggestion">';
        allSuggs.forEach(s => { html += '<li>' + escapeHtml(s) + '</li>'; });
        html += '</ul></div>';
    }

    html += '<div class="form-actions">';
    html += '<button class="btn btn-ghost" onclick="openCalibrateModal()">Calibrate (人机校准)</button>';
    html += '<button class="btn btn-primary" onclick="openModal(\'repair-modal\')">Authorize Repair (授权自愈)</button>';
    html += '</div>';
    html += '</div></div>';

    return html;
}

function metricCard(label, value, sub) {
    return '<div class="metric-card"><div class="metric-label">' + label + '</div><div class="metric-value">' + value + '</div>' + (sub ? '<div class="metric-sub">' + sub + '</div>' : '') + '</div>';
}

function scoreBarRow(label, score) {
    return '<div class="score-row"><span class="score-label">' + label + '</span>'
        + '<div class="score-bar"><div class="score-fill" style="width:' + score + '%;background:' + scoreColor(score) + '"></div></div>'
        + '<span class="score-val">' + score.toFixed(0) + '</span></div>';
}

function renderTagList(title, items, cls) {
    if (!items || items.length === 0) return '';
    let html = '<div style="margin-top:12px"><div style="font-size:12px;color:var(--text-faint);margin-bottom:6px">' + title + '</div>';
    html += '<ul class="tag-list ' + cls + '">';
    items.forEach(it => { html += '<li>' + escapeHtml(it) + '</li>'; });
    html += '</ul></div>';
    return html;
}

function autoSyncOverallGrade() {
    const acc = parseInt(document.getElementById('cal-acc-grade').value) || 4;
    const qua = parseInt(document.getElementById('cal-qua-grade').value) || 4;
    document.getElementById('cal-overall-grade').value = String(Math.min(acc, qua));
}

function openCalibrateModal() {
    if (!currentCaseData) return;
    const c = currentCaseData;
    const accGrade = c.accuracy ? (c.accuracy.overall_grade || 4) : 4;
    const quaGrade = c.quality ? (c.quality.overall_grade || 4) : 4;
    if (c.human_review) {
        document.getElementById('cal-acc-grade').value = String(c.human_review.calibrated_accuracy_grade || accGrade);
        document.getElementById('cal-qua-grade').value = String(c.human_review.calibrated_quality_grade || quaGrade);
        document.getElementById('cal-overall-grade').value = String(c.human_review.calibrated_grade || Math.min(accGrade, quaGrade));
        document.getElementById('cal-agree').value = c.human_review.is_agreed_with_ai ? 'true' : 'false';
        document.getElementById('cal-feedback').value = c.human_review.expert_feedback || '';
        document.getElementById('cal-reviewer').value = c.human_review.reviewer || 'expert_engineer';
    } else {
        document.getElementById('cal-acc-grade').value = String(accGrade);
        document.getElementById('cal-qua-grade').value = String(quaGrade);
        document.getElementById('cal-overall-grade').value = String(Math.min(accGrade, quaGrade));
        document.getElementById('cal-agree').value = 'true';
        document.getElementById('cal-feedback').value = '';
        document.getElementById('cal-reviewer').value = 'expert_engineer';
    }
    openModal('calibrate-modal');
}

// Submit calibration
async function submitCalibration() {
    const btn = document.getElementById('cal-submit');
    btn.disabled = true;
    try {
        const accGrade = parseInt(document.getElementById('cal-acc-grade').value);
        const quaGrade = parseInt(document.getElementById('cal-qua-grade').value);
        const overallGrade = parseInt(document.getElementById('cal-overall-grade').value);
        const agree = document.getElementById('cal-agree').value === 'true';
        const feedback = document.getElementById('cal-feedback').value;
        const reviewer = document.getElementById('cal-reviewer').value;
        const res = await fetch('/api/case/' + currentCaseId + '/calibrate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                calibrated_accuracy_grade: accGrade,
                calibrated_quality_grade: quaGrade,
                calibrated_grade: overallGrade,
                is_agreed_with_ai: agree,
                expert_feedback: feedback,
                reviewer: reviewer
            })
        });
        const result = await res.json();
        if (res.ok) { showToast('Calibration saved', 'success'); closeModal('calibrate-modal'); loadCase(currentCaseId); }
        else { showToast(result.detail || 'Error', 'error'); }
    } catch(e) { showToast(e.message, 'error'); }
    btn.disabled = false;
}

// Submit repair
async function submitRepair() {
    const btn = document.getElementById('repair-submit');
    btn.disabled = true;
    btn.textContent = 'Running...';
    try {
        const guidance = document.getElementById('repair-guidance').value;
        const res = await fetch('/api/case/' + currentCaseId + '/execute-repair', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({authorized: true, human_guidance: guidance})
        });
        const result = await res.json();
        if (res.ok) { showToast('Repair: ' + result.status, 'success'); closeModal('repair-modal'); loadCase(currentCaseId); }
        else { showToast(result.detail || 'Error', 'error'); }
    } catch(e) { showToast(e.message, 'error'); }
    btn.disabled = false;
    btn.textContent = 'Execute';
}

// Init
init();
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


async def start_server_async(host: str = "127.0.0.1", port: int = 8000):
    """Async entry point to launch the HITL FastAPI server within an event loop."""
    import uvicorn
    logger.info(f"Starting Eval-Agent HITL Console at http://{host}:{port}")
    config = uvicorn.Config(app=app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def start_server(host: str = "127.0.0.1", port: int = 8000):
    """Sync entry point to launch the HITL FastAPI server."""
    import uvicorn
    logger.info(f"Starting Eval-Agent HITL Console at http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start_server()
