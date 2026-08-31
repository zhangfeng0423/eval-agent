"""
seed.py — Generates realistic multi-scenario demo cases for hackathon presentation.
Aligned with the 3-Act Pitch:
  Act 1: 0.08s Fast-Fail Guardrail (0-Token Defense)
  Act 2: 5-Tier Hard-Anchored Grade & Deep Root Cause Analysis
  Act 3: Intent-Driven Self-Healing & Sandboxed Verification (Score 40 -> 85, $0.0018 cost)
"""

import os
from pathlib import Path
from .storage import AtomicJsonStorage
from .models import (
    RunResult, AccuracyResult, QualityResult, AccuracyDimensionScore,
    QualityDimensionScore, TraceMetrics, TraceSpan, PatchVerificationResult,
    HumanReviewEntry, CsvDiffResult, CaseEvalSummary
)


def seed_demo_cases(work_dir: Path):
    """Populates 4 diverse benchmark cases representing typical industrial scenarios."""
    print(f"🌱 Seeding demo evaluation cases into {work_dir}...")

    # =========================================================================
    # Case 01: SOTA Perfect Pass (Spring Boot JWT Auth & Distributed Lock)
    # =========================================================================
    c1 = work_dir / "case_01"
    c1.mkdir(parents=True, exist_ok=True)
    AtomicJsonStorage.save(str(c1 / "eval_run_result.json"), RunResult(
        status="success", attempt_count=1, exit_code=0,
        log_summary="Maven build succeeded. 24 unit tests passed. Spring Boot application smoke tests passed on port 8080.",
        run_method="llm_agent", elapsed_seconds=18.2
    ))
    AtomicJsonStorage.save(str(c1 / "eval_accuracy.json"), AccuracyResult(
        status="success", overall_grade=5, overall_score=100.0,
        dimensions=[
            AccuracyDimensionScore(dimension="核心功能完整性", grade=5, score=100.0, reason="完整实现了用户登录鉴权、Token 刷新与权限拦截器。"),
            AccuracyDimensionScore(dimension="边界防御与安全性", grade=5, score=100.0, reason="密码使用强加盐 BCrypt，无任何明文或空指针泄露风险。")
        ],
        strengths=["RESTful 分层设计严谨规范", "JWT 双 Token 刷新机制最优"],
        weaknesses=[],
        repair_suggestions=[]
    ))
    AtomicJsonStorage.save(str(c1 / "eval_quality.json"), QualityResult(
        status="success", overall_grade=5, overall_score=95.0,
        dimensions=[
            QualityDimensionScore(name="架构与工程规范", grade=5, score=100.0, comment="严格遵循 DDD 分层规范，Controller/Service/Repository 职责清晰。"),
            QualityDimensionScore(name="运行时健壮性", grade=5, score=100.0, comment="全局统一异常处理器与 Result<T> 封装完备，资源安全释放。"),
            QualityDimensionScore(name="性能与安全防线", grade=5, score=100.0, comment="HikariCP 连接池配置合理，无 SQL 注入与未授权访问漏洞。"),
            QualityDimensionScore(name="交付体验与可观测性", grade=4, score=80.0, comment="包含 Logback 结构化日志，建议在 MDC 中补充分布式 TraceID。")
        ],
        strengths=["代码达到企业生产级直接上线标准", "线程安全与并发控制极佳"],
        weaknesses=[],
        repair_suggestions=[]
    ))
    AtomicJsonStorage.save(str(c1 / "trace_metrics.json"), TraceMetrics(
        model_name="LongCat-2.0",
        total_elapsed_seconds=18.2,
        total_input_tokens=2450,
        total_output_tokens=680,
        total_tokens=3130,
        cache_hit_input_tokens=1800,
        cache_miss_input_tokens=650,
        cache_hit_rate=0.735,
        total_cost_usd=0.00175,
        spans=[
            TraceSpan(name="1. 静态依赖与语法快筛", span_type="static", status="success", elapsed_seconds=0.12, input_tokens=0, output_tokens=0, total_tokens=0, cost_usd=0.0, details="AST 快筛通过，无黑名单依赖"),
            TraceSpan(name="2. UTM/Docker 沙箱构建测试", span_type="sandbox", status="success", elapsed_seconds=12.4, input_tokens=0, output_tokens=0, total_tokens=0, cost_usd=0.0, details="Maven 24/24 单元测试通过"),
            TraceSpan(name="3. 业务功能双盲裁判", span_type="llm_agent", status="success", elapsed_seconds=2.8, input_tokens=1250, output_tokens=320, total_tokens=1570, cache_hit_input_tokens=900, cache_miss_input_tokens=350, cost_usd=0.00088, details="定级 Grade 5 (A 卓越)"),
            TraceSpan(name="4. 四大工程支柱客观打分", span_type="llm_agent", status="success", elapsed_seconds=2.88, input_tokens=1200, output_tokens=360, total_tokens=1560, cache_hit_input_tokens=900, cache_miss_input_tokens=300, cost_usd=0.00087, details="定级 Grade 5 (A 卓越)")
        ]
    ))
    AtomicJsonStorage.save(str(c1 / "human_review.json"), HumanReviewEntry(
        case_id="case_01",
        reviewer="资深架构师",
        original_score=95.0,
        calibrated_score=80.0,
        original_grade=5,
        calibrated_grade=4,
        original_accuracy_grade=5,
        calibrated_accuracy_grade=5,
        original_quality_grade=5,
        calibrated_quality_grade=4,
        is_agreed_with_ai=True,
        expert_feedback="核心功能完全正确，交付日志需补充 TraceID 注入。"
    ))

    # =========================================================================
    # Case 02: Deadlock to SOTA Self-Healing (FastAPI Stock Service)
    # =========================================================================
    c2 = work_dir / "case_02"
    c2.mkdir(parents=True, exist_ok=True)
    AtomicJsonStorage.save(str(c2 / "eval_run_result.json"), RunResult(
        status="fail", attempt_count=2, exit_code=1,
        log_summary="FastAPI application failed during startup: requests.exceptions.ConnectTimeout in event loop.",
        error_snippet="requests.exceptions.ConnectTimeout: HTTPSConnectionPool(host='api.market.example.com', port=443): Max retries exceeded with url: /v1/quotes (Caused by ConnectTimeoutError: Request timed out after 30000ms)",
        run_method="llm_agent", elapsed_seconds=32.4
    ))
    AtomicJsonStorage.save(str(c2 / "eval_accuracy.json"), AccuracyResult(
        status="success", overall_grade=3, overall_score=60.0,
        dimensions=[
            AccuracyDimensionScore(dimension="核心行情拉取逻辑", grade=4, score=80.0, reason="股票代码解析与 JSON 字段提取正确。"),
            AccuracyDimensionScore(dimension="跨期环比与差额计算", grade=2, score=40.0, reason="未处理非交易日休市与停牌股票的边界空值兜底。"),
            AccuracyDimensionScore(dimension="异常容错与超时防御", grade=1, score=20.0, reason="网络请求堵塞直接导致 ASGI 事件循环饥饿崩溃。")
        ],
        strengths=["行情字段解析算法实现完整"],
        weaknesses=["缺少非交易日空值兜底", "未对外部行情 API 进行超时防护"],
        repair_suggestions=["增加 pandas 环比差额空值填充", "在网络调用层增加超时捕获与重试机制"]
    ))
    AtomicJsonStorage.save(str(c2 / "eval_quality.json"), QualityResult(
        status="fail", overall_grade=2, overall_score=40.0,
        dimensions=[
            QualityDimensionScore(name="架构与工程规范", grade=3, score=60.0, comment="模块划分尚可，但缺少服务层隔离。"),
            QualityDimensionScore(name="运行时健壮性", grade=1, score=20.0, comment="第42行 requests.post 未设置 timeout，同步阻塞导致死锁崩溃。"),
            QualityDimensionScore(name="性能与安全防线", grade=2, score=40.0, comment="同步 I/O 阻塞了 FastAPI 主事件循环，并发吞吐量归零。"),
            QualityDimensionScore(name="交付体验与可观测性", grade=2, score=40.0, comment="缺少降级兜底日志与重试告警。")
        ],
        strengths=["路由层与工具层初步分离"],
        weaknesses=["requests.post 裸调用引发主事件循环死锁", "缺少异步非阻塞网络封装"],
        repair_suggestions=[
            "将同步 requests.post 改写为 httpx.AsyncClient 异步非阻塞调用",
            "设置 timeout=15 并增加 3 次指数退避重试与降级缓存兜底"
        ]
    ))
    AtomicJsonStorage.save(str(c2 / "patch_result.json"), PatchVerificationResult(
        patch_applied=True,
        run_after_patch_passed=True,
        score_improved=True,
        old_score=40.0,
        new_score=85.0,
        old_grade=2,
        new_grade=4,
        root_cause="第42行 requests.post 同步阻塞调用导致 FastAPI 主事件循环死锁，网络超时后崩溃",
        patch_summary="重构为 httpx.AsyncClient 异步非阻塞调用，注入 timeout=15.0s 与 3 次指数退避重试，补充 DataFrame 缺失值 fillna(0.0) 兜底",
        verification_log="""[AI-Self-Healing-Agent] 收到专家修复授权，开始执行代码手术...
1. 缺陷深度分析：定位 stock_service.py 第 42 行同步阻塞请求引发死锁
2. 代码手术重构：
   - 替换 requests.post -> await client.post (httpx.AsyncClient)
   - 注入 timeout=15.0s 与 tenacity 3 次指数退避重试
   - 补充 DataFrame 缺失值 fillna(0.0) 兜底
3. 沙箱环境复测：
   pytest tests/test_stock.py --timeout=20
   ====== 8 passed, 0 failed in 2.14s ======
4. 复测结果：沙箱运行验证全部通过！工程质量评级由 Grade 2 (40分) 跃升为 Grade 4 (85分)！"""
    ))
    AtomicJsonStorage.save(str(c2 / "trace_metrics.json"), TraceMetrics(
        model_name="DeepSeek-V4-Flash",
        total_elapsed_seconds=14.8,
        total_input_tokens=3200,
        total_output_tokens=850,
        total_tokens=4050,
        cache_hit_input_tokens=2400,
        cache_miss_input_tokens=800,
        cache_hit_rate=0.75,
        total_cost_usd=0.00115,
        spans=[
            TraceSpan(name="1. 静态代码语法分析", span_type="static", status="success", elapsed_seconds=0.09, input_tokens=0, output_tokens=0, total_tokens=0, cost_usd=0.0, details="检测到同步 requests 调用"),
            TraceSpan(name="2. 真实沙箱启动验证 (初次)", span_type="sandbox", status="fail", elapsed_seconds=5.2, input_tokens=0, output_tokens=0, total_tokens=0, cost_usd=0.0, details="ConnectTimeout 导致退出码 1"),
            TraceSpan(name="3. AI 裁判缺陷定位与 RCA 归因", span_type="llm_agent", status="success", elapsed_seconds=2.4, input_tokens=1400, output_tokens=380, total_tokens=1780, cost_usd=0.00045, details="定级 Grade 2 (40分)，产出自愈方案"),
            TraceSpan(name="4. 意图驱动代码自愈手术 (AI真改码)", span_type="llm_agent", status="success", elapsed_seconds=4.5, input_tokens=1800, output_tokens=470, total_tokens=2270, cost_usd=0.00070, details="重构为 httpx 异步客户端"),
            TraceSpan(name="5. 沙箱自动化二次复测", span_type="sandbox", status="success", elapsed_seconds=2.61, input_tokens=0, output_tokens=0, total_tokens=0, cost_usd=0.0, details="8/8 测试通过，提分至 85分！")
        ]
    ))

    # =========================================================================
    # Case 03: 0.08s Static Guardrail Intercept (0-Token Defense)
    # =========================================================================
    c3 = work_dir / "case_03"
    c3.mkdir(parents=True, exist_ok=True)
    AtomicJsonStorage.save(str(c3 / "eval_run_result.json"), RunResult(
        status="fail", attempt_count=1, exit_code=126,
        log_summary="FAST-FAIL: Static Guardrail intercepted blacklisted dependency 'event-stream@3.3.6' (Known Bitcoin Wallet Exploit).",
        error_snippet="GuardrailViolation: Dependency 'event-stream@3.3.6' failed security safety check. Dangerous sandbox execution skipped to protect host environment.",
        run_method="static_analysis", elapsed_seconds=0.08
    ))
    AtomicJsonStorage.save(str(c3 / "eval_accuracy.json"), AccuracyResult(
        status="fail", overall_grade=1, overall_score=0.0,
        dimensions=[
            AccuracyDimensionScore(dimension="安全性门禁", grade=1, score=0.0, reason="代码包含恶意供应链攻击后门，触发最高级别红线拦截。")
        ],
        strengths=[],
        weaknesses=["存在已知后门投毒恶意包"],
        repair_suggestions=["从 package.json 移除 event-stream@3.3.6 并替换为官方无害版本"]
    ))
    AtomicJsonStorage.save(str(c3 / "eval_quality.json"), QualityResult(
        status="fail", overall_grade=1, overall_score=20.0,
        dimensions=[
            QualityDimensionScore(name="性能与安全防线", grade=1, score=20.0, comment="引入了高危投毒第三方依赖，已被静态护栏在 0.08 秒内秒级拦截！")
        ],
        strengths=[],
        weaknesses=["依赖清单中包含已知后门恶意包"],
        repair_suggestions=["从 package.json 中剔除 event-stream@3.3.6 并替换为官方安全版本"]
    ))
    AtomicJsonStorage.save(str(c3 / "trace_metrics.json"), TraceMetrics(
        model_name="guardrail-ast",
        total_elapsed_seconds=0.08,
        total_input_tokens=0,
        total_output_tokens=0,
        total_tokens=0,
        cache_hit_input_tokens=0,
        cache_miss_input_tokens=0,
        cache_hit_rate=1.0,
        total_cost_usd=0.0,
        spans=[
            TraceSpan(name="1. AST 坏依赖与静态安全快筛", span_type="static", status="fail", elapsed_seconds=0.08, input_tokens=0, output_tokens=0, total_tokens=0, cost_usd=0.0, details="0 Token / 0.08s 成功拦截恶意包 event-stream@3.3.6")
        ]
    ))

    # =========================================================================
    # Case 04: Data Verification & Memory Leak Healing (Financial Batch Diff)
    # =========================================================================
    c4 = work_dir / "case_04"
    c4.mkdir(parents=True, exist_ok=True)
    AtomicJsonStorage.save(str(c4 / "eval_run_result.json"), RunResult(
        status="success", attempt_count=1, exit_code=0,
        log_summary="Financial batch computation completed. Generated report_2026.csv (10,000 records).",
        run_method="llm_agent", elapsed_seconds=8.6
    ))
    AtomicJsonStorage.save(str(c4 / "eval_csv_diff.json"), CsvDiffResult(
        status="success",
        matched_ratio=0.985,
        total_rows=10000,
        matched_rows=9850,
        diff_rows=150,
        details={"discrepancies": [{"row": 42, "field": "tax_rate", "expected": "0.060", "actual": "0.062"}]}
    ))
    AtomicJsonStorage.save(str(c4 / "eval_accuracy.json"), AccuracyResult(
        status="success", overall_grade=4, overall_score=85.0,
        dimensions=[
            AccuracyDimensionScore(dimension="万条数据计算一致性", grade=4, score=85.0, reason="98.5% 账单金额计算完全精确一致，仅存在千分之二浮点微差。"),
            AccuracyDimensionScore(dimension="多币种跨国税率换算", grade=4, score=85.0, reason="四舍五入规则在个别边际场景与国家标准有 0.002 浮动。")
        ],
        strengths=["大数据量批量计算吞吐极快", "准确率达到 98.5%"],
        weaknesses=["微小浮点精度丢失"],
        repair_suggestions=["使用 decimal.Decimal 替换 float 进行金融精度计费"]
    ))
    AtomicJsonStorage.save(str(c4 / "eval_quality.json"), QualityResult(
        status="success", overall_grade=4, overall_score=88.0,
        dimensions=[
            QualityDimensionScore(name="架构与工程规范", grade=5, score=100.0, comment="函数式流式处理，无内存泄漏。"),
            QualityDimensionScore(name="运行时健壮性", grade=4, score=80.0, comment="内存占用平稳在 80MB 内，零 OOM 风险。"),
            QualityDimensionScore(name="性能与安全防线", grade=4, score=85.0, comment="支持多线程分块并发计算。"),
            QualityDimensionScore(name="交付体验与可观测性", grade=4, score=85.0, comment="附带完整的 CSV 计算对比报告。")
        ],
        strengths=["单机万行数据处理仅耗时 8.6 秒"],
        weaknesses=[],
        repair_suggestions=["浮点精度替换为 Decimal 标准类型"]
    ))
    AtomicJsonStorage.save(str(c4 / "trace_metrics.json"), TraceMetrics(
        model_name="GLM-5.2",
        total_elapsed_seconds=8.6,
        total_input_tokens=1800,
        total_output_tokens=420,
        total_tokens=2220,
        cache_hit_input_tokens=1400,
        cache_miss_input_tokens=400,
        cache_hit_rate=0.778,
        total_cost_usd=0.00062,
        spans=[
            TraceSpan(name="1. 静态代码分析", span_type="static", status="success", elapsed_seconds=0.06, cost_usd=0.0, details="无坏依赖"),
            TraceSpan(name="2. 真实沙箱批量数据生成", span_type="sandbox", status="success", elapsed_seconds=6.1, cost_usd=0.0, details="生成 10,000 行报表"),
            TraceSpan(name="3. CSV 数据流比对校验 (Diff)", span_type="static", status="success", elapsed_seconds=0.45, cost_usd=0.0, details="匹配率 98.5%"),
            TraceSpan(name="4. 双维度裁判客观打分", span_type="llm_agent", status="success", elapsed_seconds=1.99, input_tokens=1800, output_tokens=420, total_tokens=2220, cost_usd=0.00062, details="定级 Grade 4 (88分)")
        ]
    ))

    # Auto-generate case_summary.json for each case
    for case_folder in [c1, c2, c3, c4]:
        cid = case_folder.name
        r = AtomicJsonStorage.load(str(case_folder / "eval_run_result.json"), RunResult)
        a = AtomicJsonStorage.load(str(case_folder / "eval_accuracy.json"), AccuracyResult)
        q = AtomicJsonStorage.load(str(case_folder / "eval_quality.json"), QualityResult)
        d = AtomicJsonStorage.load(str(case_folder / "eval_csv_diff.json"), CsvDiffResult)
        p = AtomicJsonStorage.load(str(case_folder / "patch_result.json"), PatchVerificationResult)
        h = AtomicJsonStorage.load(str(case_folder / "human_review.json"), HumanReviewEntry)
        t = AtomicJsonStorage.load(str(case_folder / "trace_metrics.json"), TraceMetrics)
        
        is_pass = (r.status == "success") if r else False
        if q and q.overall_grade is not None and q.overall_grade < 3:
            is_pass = False
        if a and a.overall_grade is not None and a.overall_grade < 3:
            is_pass = False

        summary = CaseEvalSummary(
            case_id=cid,
            run_result=r,
            accuracy_result=a,
            quality_result=q,
            csv_diff_result=d,
            patch_result=p,
            human_review=h,
            trace_metrics=t,
            overall_verdict="PASS" if is_pass else "FAIL",
            total_elapsed_seconds=r.elapsed_seconds if r else 0.0
        )
        AtomicJsonStorage.save(str(case_folder / "case_summary.json"), summary)

    print(f"✅ Demo cases seeded successfully: {list(sorted(p.name for p in work_dir.iterdir() if p.name.startswith('case')))}")

