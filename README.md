# 🛡️ Eval-Agent: 企业级 AI 代码生成闭环评测与自愈智能体 SDK
> **The Enterprise-Ready Multi-Agent Code Evaluation, Self-Healing & Observability Platform**
> 基于 Claude Agent SDK · 真实双盲沙箱 · 5 档硬性锚定评级 · 双维度专家校准 · 零依赖全链路可观测性

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-HITL%20Console-009688.svg)](https://fastapi.tiangolo.com)
[![Claude Agent SDK](https://img.shields.io/badge/Claude%20Agent%20SDK-MCP%20Native-purple.svg)](https://anthropic.com)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-Trace%20Ready-orange.svg)](https://opentelemetry.io)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)

---

## 📖 项目简介 (Overview)

大模型代码生成在工业界落地面临的最大痛点是：**“70% 能够通过编译的代码，在深层架构、异常健壮性、高并发死锁和安全合规上存在致命隐患（代码屎山）”**。

`Eval-Agent` 是集 **「双盲裁判 + 四大工程支柱客观定级 + 意图驱动代码自愈 + 全链路 Token/成本追踪 + 专家双维度校准 DPO 飞轮」** 于一体的企业级全闭环评测 SDK。

```
                                 ┌─────────────────────────────┐
                                 │   EvalOrchestrator (主管)   │
                                 │   (Concurrency Semaphore)   │
                                 └──────────────┬──────────────┘
                                                │
         ┌──────────────────────┬───────────────┴──────────────┬──────────────────────┐
         ▼                      ▼                              ▼                      ▼
 ┌───────────────┐      ┌───────────────┐              ┌───────────────┐      ┌───────────────┐
 │ ⚡ 静态快筛护栏 │      │ 📦 沙箱构建运行 │              │ 🎯 业务准确性  │      │ 🏗️ 工程质量   │
 │ (BadDeps AST) │      │ (UTM/OrbStack)│              │ (双盲裁判盲测) │      │ (4大工程支柱) │
 └───────┬───────┘      └───────┬───────┘              └───────┬───────┘      └───────┬───────┘
         │                      │                              │                      │
         └──────────────────────┴───────────────┬──────────────┴──────────────────────┘
                                                │
                                                ▼
                                 ┌─────────────────────────────┐
                                 │   👨‍💻 单 Case 深度评测工作台  │
                                 │ (意图自愈 / 双维度DPO / 追踪) │
                                 └─────────────────────────────┘
```

---

## 🌟 核心杀手锏亮点 (Key Highlights)

### 1. 🎯 5 档硬性锚定标准 (5-Tier Grade 1~5 / A~F)
* 彻底废除模型打 0-100 连续数字产生的随机漂移与幻觉；
* 严格遵循非黑即白的硬性锚点规范，裁判一致性高达 95%+：
  * **Grade 5 (A)**：**100 分 · 卓越**（完美无瑕，零业务逻辑漏洞，边界完备，算法最优）
  * **Grade 4 (B)**：**80 分 · 良好**（主干优秀，核心业务完全正确，仅微小次要瑕疵）
  * **Grade 3 (C)**：**60 分 · 合格**（基本可用，主干走通但遗漏非核心要求或有边界隐患）
  * **Grade 2 (D)**：**40 分 · 较差**（严重缺陷，核心计算错误或存在死锁/崩溃风险）
  * **Grade 1 (F)**：**20 分 · 失败**（致命不可用，逻辑颠倒混乱或根本未实现）

### 2. 🔍 全维度单 Case 深度评测工作台 (Deep Case Inspector)
* **功能准确性分析 (Accuracy)**：细分维度得分与判定依据、Strengths 亮点、Weaknesses 业务漏洞、Repair Suggestions 修复建议与总分进度条；
* **四大工程质量矩阵 (Quality 4 Pillars)**：架构规范、运行时健壮性、性能安全防线、交付可观测性四大支柱打分与 RCA 归因；
* **真实双盲沙箱 (Sandbox)**：运行方式、耗时、退出码与真实编译/测试运行终端日志；
* **数据比对 (CSV Diff)**：精确计算输出数据匹配率与差异 JSON。

### 3. 👨‍💻 专家双维度人机校准与 DPO 飞轮 (Dual-Dimension Calibration & DPO Flywheel)
* **独立维度纠偏**：人类专家可分别对 **Accuracy（功能准确性）** 与 **Quality（工程质量）** 独立打分校准，并设定最终综合裁决；
* **数据飞轮沉淀**：专家的每一次评分校准与纠错说明，自动追加沉淀入 `eval/expert_dataset.jsonl`，用于微调自研大模型的 DPO / RLHF 对齐。

### 4. 🛠️ 意图驱动的代码自愈闭环 (Intent-Driven Auto-Repair)
* **认知减负**：评测自动拟定自然语言综合修复策略；
* **人机协同**：专家审阅方案、输入追加指导指令（如：“增加超时重试与指数退避”），一键授权 AI 自愈 Agent 在沙箱中修改多文件代码并复测提分。

### 5. 📊 零依赖全链路可观测性 (Embedded Observability & Trace Waterfall)
* **0 额外部署、100% 离线内网安全**：无需外部 Docker/Postgres，随控制台一同启动；
* **缓存感知的 Token 追踪**：记录总输入、未命中输入、缓存命中、缓存写入、命中率、输出 Token 和单阶段费用 ($ USD / ¥ RMB)；
* **标准 OTel 协议瀑布流**：时序展示静态分析、沙箱运行、大模型裁判等各 Span 节点开销。

---

## 🚀 3 步快速上手 (Quick Start)

### 1. 安装依赖
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 一键生成测试场景与数据
```bash
python -m eval_sdk.cli seed
```

### 3. 启动全维度评测工作台
```bash
python -m eval_sdk.cli serve --port 8000
```
打开浏览器访问 [http://localhost:8000](http://localhost:8000) 即可体验！

### CLI 评测示例
```bash
# 使用 eval_config.yaml 中的默认模型和沙箱运行指定用例
python -m eval_sdk.cli 79 --work-dir /path/to/eval-agent

# 临时覆盖模型、沙箱和并发数
python -m eval_sdk.cli 79 127 --model deepseek-v4-flash --sandbox local --concurrency 2

# 仅关闭修复能力；默认不会在批处理中自动应用补丁
python -m eval_sdk.cli 79 --no-repair

# 明确允许批处理自动修复（有代码修改风险，默认不要开启）
python -m eval_sdk.cli 79 --allow-automatic-repair
```

### API Key 与模型配置
在项目根目录创建 `.env`（不要提交真实密钥）：

```dotenv
ANTHROPIC_API_KEY=your-api-key
ANTHROPIC_BASE_URL=https://your-compatible-endpoint.example.com
# 可选：仅在需要覆盖 SDK 内置 CLI 时设置
# CLAUDE_CLI_PATH=/absolute/path/to/claude
```

---

## 📈 缓存指标与成本口径

每个用例会在 `trace_metrics.json` 中保存以下指标：

| 字段 | 含义 |
| --- | --- |
| `total_input_tokens` | 总输入 Token；Claude SDK 场景包含普通输入、缓存读取和缓存写入桶 |
| `cache_hit_input_tokens` | 缓存读取命中的输入 Token |
| `cache_miss_input_tokens` | 未命中的输入 Token；缓存写入按未命中输入计入统计 |
| `cache_creation_input_tokens` | 缓存写入 Token |
| `cache_hit_rate` | `cache_hit_input_tokens / (cache_hit_input_tokens + cache_miss_input_tokens)` |
| `total_cost_usd` | 各阶段成本之和；优先使用 SDK 报告成本，缺失时按本地价格表估算 |

---

## 📁 核心模块目录结构

```text
eval-agent/
├── eval_sdk/
│   ├── models.py         # Pydantic 强类型校验、5-Tier Grade 体系、TraceSpan/TraceMetrics 数据模型
│   ├── guardrails.py     # AST/Manifest 坏依赖解析器 + 线上官方 Registry 动态校验
│   ├── sandbox.py        # UTM VM / OrbStack / Local 统一沙箱抽象
│   ├── mcp_tools.py      # 标准 Claude Agent SDK MCP 协议工具集
│   ├── agents.py         # 专职 Subagents（准确性、四大支柱质量、自愈、学习）
│   ├── orchestrator.py   # 异步信号量并发调度器 + 双盲隔离机制 + 缓存/成本追踪
│   ├── server.py         # FastAPI 单 Case 全维度深度评测与可观测性控制台
│   ├── storage.py        # 原子化 JSON 存储与 Markdown/HTML 报告生成
│   ├── seed.py           # 全场景 Demo 种子数据生成器
│   ├── cli.py            # 统一 CLI 命令行入口
│   └── skills/           # 注入大模型裁判心智的 SOP 指导文件
│       ├── eval-run-utm/SKILL.md
│       ├── eval-accuracy/SKILL.md  # 功能准确性 5 档评测规范
│       ├── eval-quality/SKILL.md   # 4 大工程支柱评测与 RCA 规范
│       └── eval-csv-diff/SKILL.md
├── eval_config.yaml      # 全局评测环境与模型配置
└── requirements.txt      # 项目依赖清单
```
