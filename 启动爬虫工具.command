#!/bin/bash
# MediaCrawler 网页配置工具 - macOS 一键启动
# 双击即可：自动启动调试 Chrome + 后端服务 + 打开网页
# 停止方法：在这个终端窗口按 Ctrl+C（调试 Chrome 保持运行，不影响）

cd "$(dirname "$0")"

echo "=========================================="
echo "  MediaCrawler 网页配置工具启动中..."
echo "=========================================="

# ---------- 1. 启动 CDP 调试 Chrome（如果还没启动） ----------
if curl -s -m 2 http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
    echo "[✓] 调试 Chrome 已在运行（端口 9222）"
else
    echo "[→] 启动调试 Chrome（端口 9222）..."
    open -na "Google Chrome" --args \
        --remote-debugging-port=9222 \
        --user-data-dir=/tmp/chrome-cdp-profile \
        --no-first-run
    # 等待 CDP 就绪（最多 15 秒）
    for i in $(seq 1 15); do
        if curl -s -m 2 http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
            echo "[✓] 调试 Chrome 已就绪"
            break
        fi
        sleep 1
        if [ "$i" -eq 15 ]; then
            echo "[✗] 调试 Chrome 启动超时，请检查是否安装了 Google Chrome"
            read -r -p "按回车退出..."
            exit 1
        fi
    done
    echo ""
    echo "  ★ 如果是第一次运行：请在弹出的 Chrome 窗口里"
    echo "    打开 douyin.com 扫码登录，登录一次后以后会记住。"
    echo ""
fi

# ---------- 2. 准备 Python 环境 ----------
# 注意：不能用 source .venv/bin/activate！激活后 VIRTUAL_ENV 会指向本目录，
# 爬虫子进程的 `uv run --active` 会误把 MediaCrawler 的依赖装进这个 venv 并清掉 flask。
cd web-config-tool
if [ ! -d .venv ]; then
    echo "[→] 首次运行，创建虚拟环境并安装依赖..."
    python3 -m venv .venv
    ./.venv/bin/pip install -q -r requirements.txt
    echo "[✓] 依赖安装完成"
fi
unset VIRTUAL_ENV  # 保险：清掉终端里可能残留的虚拟环境变量

# ---------- 3. 启动后端服务并打开网页 ----------
echo "[→] 启动后端服务: http://127.0.0.1:8080/"
( sleep 2 && open "http://127.0.0.1:8080/" ) &

echo ""
echo "=========================================="
echo "  网页即将自动打开，填写参数后点「启动爬虫」"
echo "  停止服务：在本窗口按 Ctrl+C"
echo "=========================================="
echo ""

.venv/bin/python server.py
