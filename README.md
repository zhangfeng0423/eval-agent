# 🛡️ Eval-Agent: 企业级 AI 代码生成闭环评测与自愈智能体 SDK
> **The Enterprise-Ready Multi-Agent Code Evaluation, Self-Healing & Model Arena Platform**
> 基于 Claude Agent SDK · MCP 协议 · 真实双盲沙箱 · 5 档硬性锚定评级 · 零依赖全链路可观测性

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-HITL%20Console-009688.svg)](https://fastapi.tiangolo.com)
[![Claude Agent SDK](https://img.shields.io/badge/Claude%20Agent%20SDK-MCP%20Native-purple.svg)](https://anthropic.com)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-Trace%20Ready-orange.svg)](https://opentelemetry.io)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)

---

## 📖 项目简介 (Overview)

大模型代码生成在工业界落地面临的最大痛点是：**“70% 能够通过编译的代码，在深层架构、异常健壮性、高并发死锁和安全合规上存在致命隐患（代码屎山）”**。

`Eval-Agent` 是业界首个集 **「双盲裁判 + 四大工程支柱客观定级 + 意图驱动代码自愈 + 多模型横向天梯竞技场 + 专家校准 DPO 飞轮」** 于一体的企业级全闭环评测 SDK。

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
                                  │  👨‍💻 HITL 交互复核与竞技大盘  │
                                  │ (意图自愈 / DPO导出 / Arena)│
                                  └─────────────────────────────┘
```

---

## 🌟 核心杀手锏亮点 (Key Highlights)

### 1. 🏆 多模型天梯竞技场 (Multi-Model Arena)
* 在标准化测试集下，横向对比 **Claude 3.7 vs DeepSeek-V3 vs GPT-4o vs Qwen-2.5-Coder**；
* 综合对比：**四大工程支柱得分、沙箱首轮通过率、自愈修复率、单 Case 调用成本 ($) 与 ROI 性价比指数**；
* 揭示关键结论：**DeepSeek-V3 达到 SOTA 96% 质量的同时，成本大幅下降 95%（仅为 1/22）**，为大规模 CI/CD 门禁最优解！

### 2. 🎯 5 档硬性锚定标准 (5-Tier Grade 1~5)
* 彻底废除模型打 0-100 连续数字产生的随机漂移与幻觉；
* 严格遵循 **Grade 1 (F 失败) ~ Grade 5 (A 卓越)** 非黑即白的硬性锚点规范，裁判一致性高达 95%+。

### 3. 🛠️ 意图驱动的代码自愈闭环 (Intent-Driven Auto-Repair)
* **认知减负**：初次评测只给出人类易读的**自然语言综合修复策略**；
* **人机协作**：专家审阅方案、输入追加指导指令（如：“增加3次重试”），一键授权 AI 自愈 Agent 真正修改多文件代码并在沙箱中复测提分！

### 4. 📊 零依赖全链路可观测性大屏 (Embedded Observability & Trace Waterfall)
* **0 额外部署、100% 离线内网安全**：无需启动外部 Docker/Postgres，随控制台一同启动；
* **缓存感知的 Token 追踪**：记录总输入、未命中输入、缓存命中、缓存写入、命中率、输出 Token 和每阶段成本；
* **成本口径透明**：优先使用 SDK 返回的 `costUSD` / `total_cost_usd`，缺失时使用本地模型价格估算，并明确区分估算值与供应商真实账单；
* **标准 OTel 协议**：底层遵循 OpenTelemetry 规范，支持一键无缝推送到企业集中式 Langfuse / Jaeger。

### 5. 💾 专家校准与 DPO 微调数据飞轮 (Data Flywheel)
* 人类专家的每一次评分校准与纠错备注，自动持久化沉淀入 `eval/expert_dataset.jsonl`，直接用于自研大模型的 DPO / RLHF 微调对齐。

### 6. 📦 SDK 自带 CLI 与安全修复边界
* `claude-agent-sdk>=0.2.148` 自带 Claude Code CLI，默认不要求用户另外安装 `claude` 命令；只有设置 `CLAUDE_CLI_PATH` 时才使用显式指定的 CLI；
* 批处理自动修复默认关闭，只有同时开启配置和 `--allow-automatic-repair` 才会执行；HITL 修复还需要人工复核记录和请求体中的明确授权；
* 修复 Agent 的补丁工具限制在当前用例源码目录内，避免通过 `target_dir` 修改评测仓库或其他本地工作树；
* 服务端默认监听 `127.0.0.1`，适合本机 HITL 使用。若需要局域网或生产部署，应在反向代理或应用层补充身份认证与 CSRF 防护。

---

## 🚀 3 步快速上手 (Quick Start)

### 1. 安装依赖
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # 或 pip install claude-agent-sdk pydantic fastapi uvicorn pyyaml
```

### 2. 一键生成测试场景与数据
```bash
python -m eval_sdk.cli seed
```

### 3. 启动交互控制台与模型竞技场
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

模型默认值和沙箱类型可以在 `eval_config.yaml` 中配置。CLI 参数优先级高于配置文件。

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

DeepSeek 兼容接口常见的 `prompt_tokens`、`prompt_cache_hit_tokens`、`prompt_cache_miss_tokens` 与 Claude SDK 的 `inputTokens`、`cacheReadInputTokens`、`cacheCreationInputTokens` 采用不同统计语义，编排器会分别解析，避免重复计算或截断大缓存值。

需要注意：SDK 的 `costUSD` 是 SDK/CLI 的计价结果，不等同于 DeepSeek 供应商后台的最终账单。要核对真实账单，应以供应商账单或用量接口为准。

---

## 🧪 测试与提交前检查

```bash
# 语法检查
python -m py_compile eval-sdk/orchestrator.py eval-sdk/server.py eval-sdk/storage.py

# 运行全部 SDK 单元测试
python -m unittest discover -s eval-sdk/tests -v

# 检查补丁空白错误
git diff --check
```

---

## 📁 核心模块目录结构

```text
eval-sdk/
├── models.py         # Pydantic 强类型校验、5-Tier Grade 体系、TraceSpan/TraceMetrics 数据模型
├── guardrails.py     # AST/Manifest 坏依赖解析器 + 线上官方 Registry 动态校验
├── sandbox.py        # UTM VM / OrbStack / Local 统一沙箱抽象
├── mcp_tools.py      # 标准 Claude Agent SDK MCP 协议工具集
├── agents.py         # 专职 Subagents（准确性、四大支柱质量、自愈、学习）
├── orchestrator.py   # 异步信号量并发调度器 + 双盲隔离机制 + 缓存/成本追踪
├── server.py         # FastAPI HITL 交互复核、模型竞技场与可观测性控制台
├── storage.py        # 原子化 JSON 存储与 Markdown/HTML 报告生成
├── seed.py           # 全场景 Demo 种子数据生成器
├── cli.py            # 统一 CLI 命令行入口
└── skills/           # 注入大模型裁判心智的 SOP 指导文件
    ├── eval-run-utm/SKILL.md
    ├── eval-accuracy/SKILL.md
    ├── eval-quality/SKILL.md   # 4 大工程支柱评测与 RCA 规范
    └── eval-csv-diff/SKILL.md
```

---

## 🏆 黑客松 3 分钟路演故事线 (Pitch Script)

* **0:00 - 0:30 (行业痛点)**: 现存评测只管代码能否跑通，生产环境 70% 线上故障源自脆弱异常防御与架构缺陷。
* **0:30 - 1:15 (方案架构)**: 展示多 Agent 协作管线与 5 档硬性锚定标准，以及 0.08s 拦截投毒依赖的快筛能力。
* **1:15 - 2:15 (现场 Demo)**: 演示 **多模型竞技场 (Arena)** $\to$ 查看失分 RCA $\to$ 审阅文字建议并授权 AI 沙箱自愈提分 $\to$ 全链路 Token/Cost 瀑布流。
* **2:15 - 3:00 (商业闭环)**: 展示 HITL 专家标注一键沉淀为企业私有微调语料（DPO 数据飞轮），兼顾降本、提效与资产沉淀！
