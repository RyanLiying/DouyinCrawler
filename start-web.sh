#!/usr/bin/env bash
# 启动 MediaCrawler 网页配置工具（WSL2 版）
#
# 会自动准备运行环境：
#   - 把 uv 加入 PATH（server.py 会用 `uv run` 启动爬虫）
#   - 设置 LD_LIBRARY_PATH，让 MediaCrawler 启动 Chromium 时能找到 libnss3 等库
#   - 取消激活的 venv（避免 `uv run --active` 误用 web-config-tool 的 venv）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HOME/.local/bin:${PATH}"
export LD_LIBRARY_PATH="$HOME/.local/chromium-deps/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
unset VIRTUAL_ENV

export PORT="${PORT:-8082}"
cd "${ROOT}/web-config-tool"

echo "[INFO] 启动网页配置工具: http://127.0.0.1:${PORT}"
exec .venv/bin/python server.py
