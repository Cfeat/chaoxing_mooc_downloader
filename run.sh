#!/usr/bin/env bash
# 使用本地 venv + 本地 Chromium 运行工具
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="$(pwd)/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "未找到 .venv，请先运行: bash setup.sh"
  exit 1
fi

export PLAYWRIGHT_BROWSERS_PATH="$(pwd)/.playwright-browsers"
exec "$PYTHON" -m chaoxing_dl "$@"
