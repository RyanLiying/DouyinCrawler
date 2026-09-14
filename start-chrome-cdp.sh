#!/usr/bin/env bash
# 启动 CDP 调试专用 Chromium（WSLg/WSL2 版）
#
# 用途：MediaCrawler 的「CDP 模式 + 连接已打开的浏览器」需要一个带远程调试端口的浏览器。
# 本脚本使用 Playwright 自带的 Chrome for Testing，并加载本地解压的依赖库（无需 sudo）。
#
# 首次运行后请在弹出的窗口里手动登录抖音（扫码），登录态会缓存在 PROFILE 目录，后续复用。
# 停止：Ctrl+C 或 kill $(cat /tmp/chrome-cdp.pid)
set -euo pipefail

PORT="${CDP_DEBUG_PORT:-9222}"
PROFILE="${CHROME_CDP_PROFILE:-/tmp/chrome-cdp-profile}"
LIBDIR="$HOME/.local/chromium-deps/usr/lib/x86_64-linux-gnu"
LOG="${CHROME_CDP_LOG:-/tmp/chrome-cdp.log}"
PIDFILE="${CHROME_CDP_PIDFILE:-/tmp/chrome-cdp.pid}"

CHROME="$(ls -d "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux64/chrome 2>/dev/null | head -1 || true)"
if [[ -z "${CHROME}" ]]; then
  echo "[ERROR] 未找到 Playwright Chromium。请先运行：" >&2
  echo "  cd MediaCrawler && .venv/bin/playwright install chromium" >&2
  exit 1
fi
if [[ ! -d "${LIBDIR}" ]]; then
  echo "[WARN] 未找到本地依赖库目录 ${LIBDIR}，尝试直接启动（可能缺少 libnss3 等）。" >&2
fi

# WSL2 下通过 WSLg 显示 GUI
export DISPLAY="${DISPLAY:-:0}"

echo "[INFO] 启动 CDP Chromium"
echo "       端口: ${PORT}"
echo "       配置目录: ${PROFILE}"
echo "       浏览器: ${CHROME}"

LD_LIBRARY_PATH="${LIBDIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" \
nohup "${CHROME}" \
  --remote-debugging-port="${PORT}" \
  --remote-debugging-address=127.0.0.1 \
  --user-data-dir="${PROFILE}" \
  --no-first-run --no-default-browser-check \
  --no-sandbox --disable-gpu \
  >"${LOG}" 2>&1 &
echo $! > "${PIDFILE}"

# 等待 CDP 就绪
for i in $(seq 1 30); do
  if curl -s -m 2 "http://127.0.0.1:${PORT}/json/version" >/dev/null 2>&1; then
    echo "[OK] CDP 已就绪: http://127.0.0.1:${PORT}/json/version"
    echo "[OK] PID: $(cat "${PIDFILE}")  日志: ${LOG}"
    echo "[提示] 在浏览器窗口里登录抖音后，再回网页点击「启动爬虫」。"
    exit 0
  fi
  sleep 1
done

echo "[ERROR] CDP 在 ${PORT} 端口 30 秒内未就绪，请查看日志: ${LOG}" >&2
exit 1
