# 🅰️ Eval-Agent: 给 AI 写的代码发成绩单（A–F）
> **一段代码，0.08 秒快筛，秒出 Grade —— 能编译，不代表是 A。**
> 基于 Claude Agent SDK · 四大工程支柱客观评级 · 稳定可复现的硬锚定 · 零依赖全链路可观测性

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-HITL%20Console-009688.svg)](https://fastapi.tiangolo.com)
[![Claude Agent SDK](https://img.shields.io/badge/Claude%20Agent%20SDK-MCP%20Native-purple.svg)](https://anthropic.com)
[![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-Trace%20Ready-orange.svg)](https://opentelemetry.io)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)

---

## 📖 简介 (Overview)

大模型生成的代码，**70% 能通过编译**，但深层架构、异常健壮性、高并发死锁和安全合规上藏着致命隐患。

Eval-Agent 给代码发 **A–F 成绩单**——不是 0-100 的主观印象分，而是：

- **四大工程支柱**客观分解（架构 / 健壮性 / 并发 / 安全合规），每根支柱都有分项证据与 RCA
- **可复现的硬锚定评级**：同一段代码，系统两次给出同一个 Grade（普通 AI 打分会漂移，我们不改口）
- **0.08 秒坏依赖快筛**：评级之前，先抓投毒依赖
- **全程成本可追踪**：评测一次几毛钱，每一行代码都测得起

```
                              ┌─────────────────────────────┐
                              │   EvalOrchestrator (主管)   │
                              │   (Concurrency Semaphore)   │
                              └──────────────┬──────────────┘
                                             │
      ┌──────────────────────┬───────────────┴──────────────┬──────────────────────┐
      ▼                      ▼                              ▼                      ▼
┌───────────────┐      ┌───────────────┐              ┌───────────────┐      ┌───────────────┐
│ ⚡ 静态快筛护栏 │      │  📦 沙箱执行    │              │ 🎯 业务准确性  │      │ 🏗️ 工程质量   │
│ (BadDeps AST) │      │ (local/UTM)   │              │ (双盲裁判盲测) │      │ (4大工程支柱) │
└───────┬───────┘      └───────┬───────┘              └───────┬───────┘      └───────┬───────┘
        │                      │                              │                      │
        └──────────────────────┴───────────────┬──────────────┴──────────────────────┘
                                               │
                                               ▼
                              ┌─────────────────────────────┐
                              │   👨💻 HITL 评级控制台       │
                              │ (A–F Badge / Calibrate 校准) │
                              └─────────────────────────────┘
```

---

## 🌟 核心亮点 (Key Highlights)

### 1. 🅰️ A–F 硬锚定评级（5-Tier Grade，不漂移）
* 废除模型打 0-100 连续数字产生的随机漂移与幻觉，严格遵循非黑即白的硬性锚点，裁判一致性高达 95%+：
  * **Grade 5 (A)**：**100 分 · 卓越**（完美无瑕，零业务逻辑漏洞，边界完备，算法最优）
  * **Grade 4 (B)**：**80 分 · 良好**（主干优秀，核心业务完全正确，仅微小次要瑕疵）
  * **Grade 3 (C)**：**60 分 · 合格**（基本可用，主干走通但遗漏非核心要求或有边界隐患）
  * **Grade 2 (D)**：**40 分 · 较差**（严重缺陷，核心计算错误或存在死锁/崩溃风险）
  * **Grade 1 (F)**：**20 分 · 失败**（致命不可用，逻辑颠倒混乱或根本未实现）
* 界面以 **A (G5) / B (G4) / C (G3) / D (G2) / F (G1)** 字母徽章（Badge）展示，一眼识别等级与档位。

### 2. 🔍 全维度单 Case 深度评测（有证据，不是一句话）
* **功能准确性 (Accuracy)**：细分维度得分与判定依据、Strengths 亮点、Weaknesses 业务漏洞、Repair Suggestions 建议与总分进度条；
* **四大工程质量矩阵 (Quality 4 Pillars)**：架构规范、运行时健壮性、性能安全防线、交付可观测性四大支柱打分与 RCA 归因；
* **真实沙箱运行**：运行方式、耗时、退出码与真实编译/测试运行终端日志；
* **数据比对 (CSV Diff)**：精确计算输出数据匹配率与差异 JSON。

### 3. ⚡ 0.08 秒坏依赖快筛
* AST / Manifest 解析 + 线上官方 Registry 动态校验，在评级之前先拦截投毒/坏依赖（`BadDeps AST`）。

### 4. 👨💻 人工校准入口（Calibrate）
* HITL 控制台内每档评级可人工校准（A=100 卓越 / B=80 良好 / C=60 合格 / D=40 较差 / F=20 失败）；
* 每一次校准与纠错备注自动沉淀入 `eval/expert_dataset.jsonl`，持续积累评测语料。

### 5. 📊 零依赖全链路可观测性
* 0 额外部署、100% 离线内网安全：无需外部 Docker/Postgres，随控制台一同启动；
* 缓存感知的 Token 追踪（命中率、写入、各阶段成本），成本口径透明（SDK 报告优先，缺失时本地估算并明确区分）；
* 标准 OTel 协议瀑布流，支持一键推送 Langfuse / Jaeger。

---

## 🚀 快速上手 (Quick Start)

### 第 0 步：先看效果（零依赖）
仓库已内置 **3 个真实评测 case 的结果**，不装任何环境也能看：
```text
case_01/eval_run_result.json   # 运行结果与评级
case_01/eval_accuracy.json     # 业务准确性评测
case_01/eval_quality.json      # 四大工程支柱评测
```
（case_02 / case_03 同理。）想自己上手跑，再走下面三步。

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

### 3. 启动评级控制台
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
```

### API Key 与模型配置
在项目根目录创建 `.env`（不要提交真实密钥）：

```dotenv
ANTHROPIC_API_KEY=your-api-key
ANTHROPIC_BASE_URL=https://your-compatible-endpoint.example.com
# 可选：仅在需要覆盖 SDK 内置 CLI 时设置
# CLAUDE_CLI_PATH=/absolute/path/to/claude
```

模型默认值和沙箱类型在 `eval_config.yaml` 中配置。CLI 参数优先级高于配置文件。

---

## 📁 Case 目录规范与沙箱

### 被测项目源码放哪里（`mnt` 约定）
系统约定被测项目源码放在 `case_<ID>/mnt/` 下。`mnt` = **mount（挂载）**，表示"被测源码的挂载根"，也是补丁工具的白名单边界，防止越权改写 `eval_*.json`、`case_summary.json` 等评测数据。

> 该约定已做**自适应**，源码直接放 `case_<ID>/` 根目录同样支持（修复逻辑会自动回退识别源码根）。

### 沙箱三种模式
| 模式 | 实现 | 适用场景 |
| --- | --- | --- |
| `local`（默认） | 本机 `subprocess` 直接执行 | 最快，无需任何虚拟机，适合本机 Demo |
| `utm` | UTM 虚拟机（ssh `127.0.0.1:2222`） | 需要先启动 UTM VM |
| `orbstack` | OrbStack 容器 | 已安装 OrbStack |

> ⚠️ `local` 为宿主机直接执行，**仅限本机 / 可信环境使用**，请勿对多人或公网开放。

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

DeepSeek 兼容接口的 `prompt_tokens` / `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` 与 Claude SDK 的 `inputTokens` / `cacheReadInputTokens` / `cacheCreationInputTokens` 统计语义不同，编排器会分别解析，避免重复计算或截断大缓存值。

需要注意：SDK 的 `costUSD` 是 SDK/CLI 的计价结果，不等同于供应商后台的最终账单。要核对真实账单，应以供应商账单或用量接口为准。

---

## 🧪 测试与提交前检查

```bash
# 语法检查
python -m py_compile eval_sdk/orchestrator.py eval_sdk/server.py eval_sdk/storage.py

# 运行全部 SDK 单元测试
python -m unittest discover -s eval_sdk/tests -v

# 检查补丁空白错误
git diff --check
```

---

## 📁 核心模块目录结构

```text
eval-agent/
├── eval_sdk/
│   ├── models.py         # Pydantic 强类型校验、A-F Grade 体系、TraceSpan/TraceMetrics 数据模型
│   ├── guardrails.py     # AST/Manifest 坏依赖解析器 + 线上官方 Registry 动态校验
│   ├── sandbox.py        # local / UTM VM / OrbStack 统一沙箱抽象
│   ├── mcp_tools.py      # 标准 Claude Agent SDK MCP 协议工具集
│   ├── agents.py         # 专职 Subagents（准确性、四大支柱质量、校准）
│   ├── orchestrator.py   # 异步信号量并发调度器 + 双盲隔离机制 + 缓存/成本追踪
│   ├── server.py         # FastAPI HITL 评级控制台与可观测性界面
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

---

## 🗺️ Roadmap

- **⚡ 深度评测并行化（近期可做）**：Accuracy 与 Quality 两个评测阶段当前串行执行（单 case 深度评测约 10 分钟）；二者相互独立、不共享上下文（均只读源码，且明确禁止读取彼此的评测产物），可 `asyncio.gather` 并行，预计省约 1/3 耗时。
- **📉 上下文瘦身，砍掉 Token 浪费（近期可做）**：单 case 深度评测累计消耗百万级输入 Token——被测源码本身很小（如 219 行），大头来自 Agent 在工具循环中反复 Read/Grep、每次调用携带全量历史上下文。将源码一次性嵌入 Prompt、限制重复读取，可显著降本提效。
- **代码自愈修复（开发中）**：HITL 授权后由 AI 真正修改代码并在沙箱复测提分。当前由 `server.py` 顶部 `REPAIR_ENABLED` 控制、默认 `False`（暂时关闭）；恢复时改回 `True` 并重启。恢复后保留人工授权与补丁目录边界。
- **DPO / RLHF 微调数据飞轮**：把 `eval/expert_dataset.jsonl` 的校准语料喂回自研模型训练对齐。

---

## 🔒 安全边界

- 服务端默认监听 `127.0.0.1`，适合本机 HITL 使用；
- 默认沙箱为 **local**（宿主机直接执行）——**仅限本机 Demo / 可信环境**，不要开放为多人或公网服务；多人/生产部署请启用容器或虚拟机沙箱，并补充身份认证与 CSRF 防护。
