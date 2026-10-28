# Eval-Agent

给 AI 生成的代码提供功能、工程质量与运行证据的评测原型。

A Python prototype for reviewing AI-generated code with execution results, structured quality assessments, and human review.

## 项目状态

这是用于本地实验的评测工具。仓库包含 Claude Agent SDK 编排、FastAPI 人工复核控制台、静态依赖检查及示例评测结果。它不构成生产环境的质量或安全保证。

- 功能准确性与工程质量分别评估，以 A / B / C / D / F 五档展示结果。
- 用例结果保留运行日志、评测 JSON、差异及 token / 成本记录。
- 人工校准可积累评测语料；控制台代码修复入口当前由 `REPAIR_ENABLED = False` 关闭。
- 支持 local、UTM 与 OrbStack 执行方式。当前配置使用 local，在宿主机直接执行被测代码，仅运行可信用例。

评级一致性、检查耗时与每次成本取决于模型、输入和运行环境；目前 README 未提供可复现的对照基准，因此不承诺固定数值或确定性结果。

## 无需运行即可查看

先读随仓库保存的样例：

- [运行结果](case_01/eval_run_result.json)
- [功能准确性评估](case_01/eval_accuracy.json)
- [工程质量评估](case_01/eval_quality.json)
- [用量与成本记录](case_01/trace_metrics.json)

这些是已有运行产物，不代表当前环境重新跑测结果。

## 本地启动

```bash
git clone https://github.com/zhangfeng0423/eval-agent.git
cd eval-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，配置自己的 ANTHROPIC_API_KEY 和兼容接口地址
python -m eval_sdk.cli serve --port 8000
```

访问 http://localhost:8000 。控制台默认监听 `127.0.0.1`。

也可以执行 `bash setup.sh`。首次运行会生成 `.env` 并提示填写配置；再次运行会生成演示数据后启动控制台。`seed` 会写入演示用例，请在独立克隆中使用，避免覆盖自己的用例。

模型和沙箱配置见 [eval_config.yaml](eval_config.yaml)。不要提交真实密钥。深度评测会调用模型 API，实际费用以供应商账单为准。

### CLI 评测

```bash
# 被测源码通常位于 case_<ID>/mnt/；请先准备自己的可信用例
python -m eval_sdk.cli 79 --work-dir /path/to/cases --sandbox local --no-repair
# 多用例并发；模型名按实际服务可用情况填写
python -m eval_sdk.cli 79 127 --model YOUR_MODEL --sandbox local --concurrency 2 --no-repair
```

## 代码入口

| 路径 | 用途 |
| --- | --- |
| [eval-sdk/cli.py](eval-sdk/cli.py) | 命令行与配置加载 |
| [eval-sdk/orchestrator.py](eval-sdk/orchestrator.py) | 评测阶段编排与用量追踪 |
| [eval-sdk/guardrails.py](eval-sdk/guardrails.py) | 依赖解析及 Registry 检查 |
| [eval-sdk/sandbox.py](eval-sdk/sandbox.py) | 执行环境适配 |
| [eval-sdk/server.py](eval-sdk/server.py) | 人工复核控制台 |
| [eval-sdk/storage.py](eval-sdk/storage.py) | 结果存储与报告 |
| [eval-sdk/skills](eval-sdk/skills) | 各阶段评测规范 |

`eval_sdk` 是指向 `eval-sdk` 的符号链接，Python 模块命令使用下划线；查看源码使用上表的真实目录。

## 开发检查

安装依赖后可运行：

```bash
python -m py_compile eval_sdk/orchestrator.py eval_sdk/server.py eval_sdk/storage.py
python -m unittest discover -s eval_sdk/tests -v
git diff --check
```

## 限制与后续方向

- local 模式没有进程隔离；面向不可信代码或多人使用前，需要隔离、身份验证及其他部署防护。
- 模型评判可能变化，需结合运行证据与人工复核；成本可能是 SDK 报告或本地估算。
- 并行评测、上下文压缩和校准数据用于训练仍是后续探索，不作为已完成能力展示。
- 当前仓库没有 LICENSE 文件；本说明不授予额外使用许可。许可证由维护者另行确认。

问题和复现步骤可提交到 [Issues](https://github.com/zhangfeng0423/eval-agent/issues)。
