"""
seed.py — Generates realistic multi-scenario demo cases for hackathon and presentation testing.
"""

import os
from pathlib import Path
from .storage import AtomicJsonStorage
from .models import (
    RunResult, AccuracyResult, QualityResult, AccuracyDimensionScore,
    QualityDimensionScore, TraceMetrics, TraceSpan
)


def seed_demo_cases(work_dir: Path):
    """Populates 4 diverse benchmark cases representing typical industrial scenarios."""
    print(f"🌱 Seeding demo evaluation cases into {work_dir}...")

    # Case 01: SOTA Perfect Pass (Spring Boot JWT Auth)
    c1 = work_dir / "case_01"
    c1.mkdir(parents=True, exist_ok=True)
    AtomicJsonStorage.save(str(c1 / "eval_run_result.json"), RunResult(
        status="success", attempt_count=1, exit_code=0,
        log_summary="Maven build succeeded. Spring Boot application smoke tests passed on port 8080.",
        run_method="llm_agent", elapsed_seconds=18.2
    ))
    AtomicJsonStorage.save(str(c1 / "eval_accuracy.json"), AccuracyResult(
        status="success", overall_grade=5, overall_score=100.0,
        dimensions=[
            AccuracyDimensionScore(dimension="核心功能完整性", grade=5, score=100.0, reason="完整实现了用户登录鉴权与Token拦截。"),
            AccuracyDimensionScore(dimension="边界防御与安全性", grade=5, score=100.0, reason="密码使用强加盐BCrypt，无明文泄露。")
        ],
        strengths=["RESTful分层设计严谨", "JWT加解密算法最优"],
        weaknesses=[],
        repair_suggestions=[]
    ))
    AtomicJsonStorage.save(str(c1 / "eval_quality.json"), QualityResult(
        status="success", overall_grade=5, overall_score=100.0,
        dimensions=[
            QualityDimensionScore(name="架构与工程规范", grade=5, score=100.0, comment="高内聚低耦合，符合官方规范。"),
            QualityDimensionScore(name="运行时健壮性", grade=5, score=100.0, comment="全局异常拦截器与统一响应封装完备。"),
            QualityDimensionScore(name="性能与安全防线", grade=5, score=100.0, comment="无SQL注入漏洞，并发连接池配置合理。"),
            QualityDimensionScore(name="交付体验与可观测性", grade=4, score=80.0, comment="包含结构化日志，建议注入TraceID。")
        ],
        strengths=["代码达到企业生产级上线标准"],
        weaknesses=[],
        repair_suggestions=[]
    ))

    # Case 02: Deadlock / Timeout with Self-Healing (FastAPI Stock Fetcher)
    c2 = work_dir / "case_02"
    c2.mkdir(parents=True, exist_ok=True)
    AtomicJsonStorage.save(str(c2 / "eval_run_result.json"), RunResult(
        status="fail", attempt_count=2, exit_code=1,
        log_summary="FastAPI application failed during startup: requests.exceptions.ConnectTimeout.",
        error_snippet="requests.exceptions.ConnectTimeout: HTTPSConnectionPool(host='api.bochaai.com', port=443): Max retries exceeded",
        run_method="llm_agent", elapsed_seconds=32.4
    ))
    AtomicJsonStorage.save(str(c2 / "eval_accuracy.json"), AccuracyResult(
        status="success", overall_grade=3, overall_score=60.0,
        dimensions=[
            AccuracyDimensionScore(dimension="核心业务功能", grade=3, score=60.0, reason="缺少平安银行跨年度报表比对计算。"),
            AccuracyDimensionScore(dimension="边界与异常容错", grade=2, score=40.0, reason="网络请求堵塞直接导致服务宕机。")
        ],
        strengths=["股票代码识别准确"],
        weaknesses=["未处理网络超时与非交易日容错"],
        repair_suggestions=["增加 pandas 环比差额计算", "网络请求层增加超时捕获与重试机制"]
    ))
    AtomicJsonStorage.save(str(c2 / "eval_quality.json"), QualityResult(
        status="success", overall_grade=2, overall_score=40.0,
        dimensions=[
            QualityDimensionScore(name="架构与工程规范", grade=3, score=60.0, comment="模块划分尚可，但缺少服务层抽象。"),
            QualityDimensionScore(name="运行时健壮性", grade=1, score=20.0, comment="第42行 requests.post 未设置 timeout 导致死锁。"),
            QualityDimensionScore(name="性能与安全防线", grade=3, score=60.0, comment="同步 I/O 阻塞了 FastAPI 事件循环。"),
            QualityDimensionScore(name="交付体验与可观测性", grade=2, score=40.0, comment="缺少重试与降级日志。")
        ],
        strengths=["工具层与业务层逻辑基本分离"],
        weaknesses=["requests.post 裸调用导致服务崩溃", "缺少异步非阻塞网络封装"],
        repair_suggestions=[
            "在 requests.post 中增加 timeout=15 并捕获 RequestException 异常",
            "改造为 httpx.AsyncClient 异步非阻塞调用，并增加 3 次指数退避重试"
        ]
    ))

    # Case 03: Static Guardrail Intercept (0.08s 0-Token Defense)
    c3 = work_dir / "case_03"
    c3.mkdir(parents=True, exist_ok=True)
    AtomicJsonStorage.save(str(c3 / "eval_run_result.json"), RunResult(
        status="fail", attempt_count=1, exit_code=126,
        log_summary="FAST-FAIL: Static Guardrail intercepted blacklisted dependency 'event-stream@3.3.6' (Known Bitcoin Wallet Exploit).",
        error_snippet="GuardrailViolation: Dependency 'event-stream@3.3.6' failed safety check. Sandbox execution skipped to prevent infection.",
        run_method="static_analysis", elapsed_seconds=0.08
    ))
    AtomicJsonStorage.save(str(c3 / "eval_quality.json"), QualityResult(
        status="fail", overall_grade=1, overall_score=20.0,
        dimensions=[
            QualityDimensionScore(name="性能与安全防线", grade=1, score=20.0, comment="引入了高危投毒第三方依赖，已被静态护栏秒级拦截！")
        ],
        strengths=[],
        weaknesses=["依赖清单中包含已知后门恶意包"],
        repair_suggestions=["从 package.json 中剔除 event-stream@3.3.6 并替换为官方安全版本"]
    ))

    print(f"✅ Demo cases seeded successfully: {list(sorted(p.name for p in work_dir.iterdir() if p.name.startswith('case')))}")
