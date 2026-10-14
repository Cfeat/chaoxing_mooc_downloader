#!/usr/bin/env bash
# 本地虚拟环境 + 国内镜像安装（macOS / Linux）
set -euo pipefail
cd "$(dirname "$0")"

PYPI="https://mirrors.aliyun.com/pypi/simple/"
PW_HOST="https://npmmirror.com/mirrors/playwright"

echo "==> 1/3 创建本地 venv (.venv)"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi

echo "==> 2/3 安装 Python 依赖 (阿里云 PyPI)"
.venv/bin/python -m pip install -U pip -i "$PYPI" --trusted-host mirrors.aliyun.com
.venv/bin/python -m pip install -r requirements.txt -i "$PYPI" --trusted-host mirrors.aliyun.com

echo "==> 3/3 安装 Chromium 到项目目录 (npmmirror)"
export PLAYWRIGHT_BROWSERS_PATH="$(pwd)/.playwright-browsers"
export PLAYWRIGHT_DOWNLOAD_HOST="$PW_HOST"
mkdir -p "$PLAYWRIGHT_BROWSERS_PATH"
.venv/bin/python -m playwright install chromium

echo
echo "完成。之后请用:"
echo "  ./run.sh login --url \"你的课程页URL\""
echo "  ./run.sh download --url \"你的课程页URL\""
