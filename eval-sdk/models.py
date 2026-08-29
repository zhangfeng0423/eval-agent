"""
models.py — Data schemas and Pydantic validation models for the Evaluation Agent SDK.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field


class DependencyType(str, Enum):
    MAVEN = "maven"
    NPM = "npm"
    PIP = "pip"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BadDependencyEntry(BaseModel):
    """Represents a learned bad dependency pattern with confidence, hit counting, and TTL."""
    id: str = Field(description="Format: type:pkg_name, e.g. maven:org.apache.poi:poi-ooxml-schemas")
    dep_type: DependencyType
    dep_name: str
    reason: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    hit_count: int = 0
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: Optional[datetime] = None

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return utc_now() > self.expires_at


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAIL = "fail"
    SKIPPED = "skipped"


class RunResult(BaseModel):
    status: str = "success"  # "success" or "fail"
    attempt_count: int = 1
    exit_code: int = 0
    log_summary: str = ""
    error_snippet: str = ""
    run_method: str = "llm_agent"  # "static_analysis" or "llm_agent"
    note: str = ""
    inspect_cmd: str = ""
    elapsed_seconds: float = 0.0


def grade_to_score(grade: int) -> float:
    """Converts 1-5 Grade to percentage score (5->100, 4->80, 3->60, 2->40, 1->20)."""
    return max(1, min(5, grade)) * 20.0


def grade_to_label(grade: int) -> str:
    labels = {
        5: "A (卓越/Excellent)",
        4: "B (良好/Good)",
        3: "C (合格/Acceptable)",
        2: "D (较差/Poor)",
        1: "F (失败/Fatal)"
    }
    return labels.get(grade, f"Grade {grade}")


class AccuracyDimensionScore(BaseModel):
    dimension: str
    grade: int = Field(default=4, ge=1, le=5, description="1-5 档位评级")
    score: float = Field(default=80.0, ge=0.0, le=100.0)
    reason: str = ""


class AccuracyResult(BaseModel):
    status: str = "success"
    overall_grade: int = Field(default=4, ge=1, le=5)
    overall_score: float = 80.0
    dimensions: List[AccuracyDimensionScore] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    repair_suggestions: List[str] = Field(default_factory=list)
    raw_output: str = ""


class QualityDimensionScore(BaseModel):
    name: str
    grade: int = Field(default=4, ge=1, le=5, description="1-5 档位评级")
    score: float = Field(default=80.0, ge=0.0, le=100.0)
    comment: str = ""


class QualityResult(BaseModel):
    status: str = "success"
    overall_grade: int = Field(default=4, ge=1, le=5)
    overall_score: float = 80.0
    dimensions: List[QualityDimensionScore] = Field(default_factory=list)
    code_structure_analysis: str = ""
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    repair_suggestions: List[str] = Field(default_factory=list)
    raw_output: str = ""


class CsvDiffResult(BaseModel):
    status: str = "success"
    matched_ratio: float = 1.0
    diff_summary: str = ""
    missing_items: List[str] = Field(default_factory=list)
    unexpected_items: List[str] = Field(default_factory=list)
    raw_output: str = ""


class PatchVerificationResult(BaseModel):
    patch_applied: bool = False
    run_after_patch_passed: bool = False
    score_improved: bool = False
    old_score: Optional[float] = None
    new_score: Optional[float] = None
    verification_log: str = ""


class HumanReviewEntry(BaseModel):
    case_id: str
    reviewer: str = "expert"
    original_score: float
    calibrated_score: float
    original_grade: int = 4
    calibrated_grade: int = 4
    is_agreed_with_ai: bool = True
    expert_feedback: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class HumanCalibrationRequest(BaseModel):
    calibrated_grade: int = Field(default=4, ge=1, le=5)
    calibrated_score: Optional[float] = None
    is_agreed_with_ai: bool = True
    expert_feedback: str = ""
    reviewer: str = "expert"


class RepairAuthorizationRequest(BaseModel):
    authorized: bool = False
    human_guidance: str = ""


class TraceSpan(BaseModel):
    name: str
    span_type: str = "llm_agent"  # "static", "sandbox", "llm_agent"
    status: str = "success"  # "success" or "fail"
    elapsed_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cache_hit_input_tokens: int = 0
    cache_miss_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_hit_rate: Optional[float] = None
    cost_usd: float = 0.0
    details: str = ""


class TraceMetrics(BaseModel):
    model_name: str = "claude-3-7-sonnet"
    total_elapsed_seconds: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    cache_hit_input_tokens: int = 0
    cache_miss_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_hit_rate: Optional[float] = None
    total_cost_usd: float = 0.0
    spans: List[TraceSpan] = Field(default_factory=list)


def calculate_llm_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """Calculates USD cost based on official model pricing per million tokens."""
    model_lower = model_name.lower()
    if "deepseek" in model_lower:
        in_rate = 0.14 / 1_000_000
        out_rate = 0.28 / 1_000_000
    elif "gpt-4o-mini" in model_lower:
        in_rate = 0.15 / 1_000_000
        out_rate = 0.60 / 1_000_000
    elif "claude-3-5-haiku" in model_lower:
        in_rate = 0.80 / 1_000_000
        out_rate = 4.00 / 1_000_000
    else:  # Claude 3.5 Sonnet / 3.7 Sonnet / default
        in_rate = 3.00 / 1_000_000
        out_rate = 15.00 / 1_000_000
    return (input_tokens * in_rate) + (output_tokens * out_rate)


class CaseEvalSummary(BaseModel):
    case_id: str
    task_type: str = "generation"  # "understanding" or "generation"
    total_elapsed_seconds: float = 0.0
    run_result: Optional[RunResult] = None
    accuracy_result: Optional[AccuracyResult] = None
    quality_result: Optional[QualityResult] = None
    csv_diff_result: Optional[CsvDiffResult] = None
    patch_result: Optional[PatchVerificationResult] = None
    human_review: Optional[HumanReviewEntry] = None
    trace_metrics: Optional[TraceMetrics] = None
    overall_verdict: str = "PASS"  # "PASS" or "FAIL"
    last_updated: datetime = Field(default_factory=utc_now)
