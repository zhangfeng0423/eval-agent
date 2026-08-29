"""
storage.py — Atomic transactional storage, Pydantic validation, and report/dashboard generation.
"""

import os
import json
import logging
from typing import Type, TypeVar, Optional, List, Dict
from pathlib import Path
from pydantic import BaseModel, ValidationError

try:
    from .models import CaseEvalSummary, RunResult, AccuracyResult, QualityResult, CsvDiffResult
except (ImportError, ValueError):
    from models import CaseEvalSummary, RunResult, AccuracyResult, QualityResult, CsvDiffResult

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class AtomicJsonStorage:
    """Provides atomic disk writes to prevent partial/corrupted files."""

    @staticmethod
    def save(filepath: str, data: BaseModel):
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp")
        
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(data.model_dump_json(indent=2))
            
        temp_path.replace(path)

    @staticmethod
    def load(filepath: str, model_cls: Type[T]) -> Optional[T]:
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            return model_cls.model_validate_json(content)
        except (ValidationError, json.JSONDecodeError, Exception) as e:
            logger.warning(f"File {filepath} exists but failed validation for {model_cls.__name__}: {e}")
            return None

    @staticmethod
    def is_completed(filepath: str, model_cls: Type[T]) -> bool:
        """Returns True only if file exists, is non-empty, and conforms to model_cls schema."""
        return AtomicJsonStorage.load(filepath, model_cls) is not None


class ReportGenerator:
    """Generates Markdown summary tables and HTML visualization dashboards."""

    @staticmethod
    def generate_markdown_summary(summaries: List[CaseEvalSummary], output_path: str):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# AI Code Evaluation & Self-Healing Benchmark Report",
            "",
            f"**Total Cases Evaluated**: {len(summaries)}",
            "",
            "| Case ID | Task Type | Run Status | Accuracy Score | Quality Score | CSV Match Ratio | Verdict | Time (s) |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
        ]

        for s in summaries:
            run_st = s.run_result.status if s.run_result else "N/A"
            acc_sc = f"{s.accuracy_result.overall_score:.1f}" if s.accuracy_result else "N/A"
            qua_sc = f"{s.quality_result.overall_score:.1f}" if s.quality_result else "N/A"
            csv_rt = f"{s.csv_diff_result.matched_ratio * 100:.1f}%" if s.csv_diff_result else "N/A"
            verdict_badge = "🟢 PASS" if s.overall_verdict == "PASS" else "🔴 FAIL"
            lines.append(
                f"| `{s.case_id}` | {s.task_type} | `{run_st}` | {acc_sc} | {qua_sc} | {csv_rt} | {verdict_badge} | {s.total_elapsed_seconds:.1f}s |"
            )

        lines.extend([
            "",
            "## Key Diagnostic Attributions & Auto-Repair Insights",
            ""
        ])

        for s in summaries:
            lines.append(f"### Case `{s.case_id}`")
            if s.quality_result:
                if s.quality_result.strengths:
                    lines.append("**Strengths**:")
                    for st in s.quality_result.strengths:
                        lines.append(f"- {st}")
                if s.quality_result.weaknesses:
                    lines.append("**Weaknesses / 失分归因**:")
                    for wk in s.quality_result.weaknesses:
                        lines.append(f"- {wk}")
                if s.quality_result.repair_suggestions:
                    lines.append("**Repair Suggestions / 修复建议**:")
                    for rs in s.quality_result.repair_suggestions:
                        lines.append(f"- {rs}")
            lines.append("")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        logger.info(f"Markdown report generated at {output_path}")

    @staticmethod
    def generate_html_dashboard(summaries: List[CaseEvalSummary], output_path: str):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        cards_html = []

        for s in summaries:
            badge_class = "pass" if s.overall_verdict == "PASS" else "fail"
            acc_score = s.accuracy_result.overall_score if s.accuracy_result else 0
            qua_score = s.quality_result.overall_score if s.quality_result else 0

            cards_html.append(f"""
            <div class="case-card {badge_class}">
                <div class="card-header">
                    <h3>Case: {s.case_id}</h3>
                    <span class="badge {badge_class}">{s.overall_verdict}</span>
                </div>
                <div class="metrics">
                    <div class="metric"><span class="label">Run Status:</span> <b>{s.run_result.status if s.run_result else 'N/A'}</b></div>
                    <div class="metric"><span class="label">Accuracy:</span> <b>{acc_score:.1f}</b></div>
                    <div class="metric"><span class="label">Quality:</span> <b>{qua_score:.1f}</b></div>
                    <div class="metric"><span class="label">Elapsed:</span> <b>{s.total_elapsed_seconds:.1f}s</b></div>
                </div>
            </div>
            """)

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>AI Code Evaluation Dashboard</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }}
        h1 {{ color: #38bdf8; font-size: 24px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; margin-top: 20px; }}
        .case-card {{ background: #1e293b; border-radius: 10px; padding: 18px; border: 1px solid #334155; }}
        .case-card.pass {{ border-left: 5px solid #10b981; }}
        .case-card.fail {{ border-left: 5px solid #ef4444; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
        .badge {{ padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }}
        .badge.pass {{ background: #065f46; color: #34d399; }}
        .badge.fail {{ background: #7f1d1d; color: #f87171; }}
        .metrics {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 13px; }}
        .metric .label {{ color: #94a3b8; }}
    </style>
</head>
<body>
    <h1>AI Code Evaluation & Self-Healing Dashboard</h1>
    <div class="grid">
        {"".join(cards_html)}
    </div>
</body>
</html>"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        logger.info(f"HTML dashboard generated at {output_path}")
