"""
eval-sdk — Autonomous Multi-Agent Code Evaluation & Self-Healing Platform.
"""

from .models import (
    CaseEvalSummary,
    RunResult,
    AccuracyResult,
    QualityResult,
    CsvDiffResult,
    BadDependencyEntry,
    DependencyType
)
from .sandbox import SandboxProvider, UTMSandbox, OrbStackSandbox, LocalSandbox, create_sandbox
from .guardrails import BadDepsStore
from .orchestrator import EvalOrchestrator

__all__ = [
    "CaseEvalSummary",
    "RunResult",
    "AccuracyResult",
    "QualityResult",
    "CsvDiffResult",
    "BadDependencyEntry",
    "DependencyType",
    "SandboxProvider",
    "UTMSandbox",
    "OrbStackSandbox",
    "LocalSandbox",
    "create_sandbox",
    "BadDepsStore",
    "EvalOrchestrator",
]
