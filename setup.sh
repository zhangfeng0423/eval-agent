#!/usr/bin/env bash
# ==============================================================================
# Eval-Agent 一键启动脚本
# 用法:  bash setup.sh
# 做三件事: 建环境 → 配 .env → 启动评级控制台
# ==============================================================================
set -euo pipefail
cd "$(dirname "$0")"

echo "==> [1/4] 创建虚拟环境 (.venv)"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate

echo "==> [2/4] 安装依赖"
pip install -q -r requirements.txt

echo "==> [3/4] 检查 .env"
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "    ⚠️  已从 .env.example 生成 .env"
  echo "    请先编辑 .env，填入你的 ANTHROPIC_API_KEY 和 ANTHROPIC_BASE_URL，再重新运行本脚本。"
  echo ""
  exit 0
fi
if ! grep -qE '^ANTHROPIC_API_KEY=.+' .env; then
  echo ""
  echo "    ⚠️  .env 中缺少 ANTHROPIC_API_KEY，请填写后再运行。"
  echo ""
  exit 1
fi

echo "==> [4/4] 生成演示数据，启动评级控制台"
python -m eval_sdk.cli seed
echo ""
echo "    ✅ 已就绪，正在启动 (沙箱: local, 端口 8000)..."
echo "    浏览器打开 http://localhost:8000   (Ctrl+C 停止)"
echo ""
exec python -m eval_sdk.cli serve --port 8000 --sandbox local
