# 抖音非遗爬虫项目

本项目用于采集抖音上与非物质文化遗产相关的内容，包含 MediaCrawler 官方仓库和一个中文网页配置工具。

## 项目结构

```
crawler/
├── start-chrome-cdp.sh    # 启动 CDP 调试专用 Chromium（WSL/Linux）
├── start-web.sh           # 启动网页配置工具（WSL/Linux）
├── MediaCrawler/          # 抖音爬虫核心库
└── web-config-tool/       # 中文网页配置与启动工具
    ├── README.md          # 详细使用说明
    ├── WORKFLOW.md        # 完整工作流
    ├── index.html         # 可视化配置页面
    └── tools/             # 后处理脚本
        ├── enrich_author_stats.py    # 作者统计后处理（访问作者主页提取粉丝数等）
        ├── merge_douyin_outputs.py   # 合并导出 3 个 CSV（主表/评论表/作者表）
        └── build_douyin_workbook.py  # 生成 3-Sheet Excel（主表/评论表/作者表）
```

## 快速启动

### 1. 环境准备

- Python 3.10+（推荐用 uv 管理）
- 安装 uv：`pip install uv`
- Node.js ≥ 16（抖音签名用 `execjs`，必须）
- Chrome / Chromium（CDP 模式需要一个带远程调试的浏览器）

### 2. 安装依赖

```bash
# 1) 进入 web-config-tool 并安装后端依赖
cd web-config-tool
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2) 进入 MediaCrawler 并安装爬虫依赖
cd ../MediaCrawler
uv sync
```

### 3. 启动 Chrome 远程调试（CDP 模式）

> 以下是 macOS 示例。**本机（WSL2/Linux）请直接用 `./start-chrome-cdp.sh`**（见「一键启动脚本」），无需手动敲命令。

日常使用的 Chrome **不用动**。用命令行单独启动一个调试专用实例（独立的用户数据目录，与日常 Chrome 互不影响）：

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-cdp-profile \
  --no-first-run
```

- 首次需在这个调试实例里手动登录抖音（登录态缓存在 `/tmp/chrome-cdp-profile` 里，后续复用（/tmp 会随系统重启清空，重启 Mac 后需重新登录一次））。
- 验证服务已就绪：`curl http://localhost:9222/json/version`，能返回 JSON 即正常。
- 旧的 `chrome://inspect` 勾选方式要求完全退出日常 Chrome 才能生效，不推荐。

### 4. 启动网页配置工具

```bash
cd web-config-tool
source .venv/bin/activate
PORT=8082 python server.py
```

默认访问地址：http://127.0.0.1:8082

### 5. 一键启动脚本（本机 WSL2/Linux 已适配）

在项目根目录执行：

```bash
./start-chrome-cdp.sh   # 启动带远程调试的 Chromium（首次需在弹出的窗口里登录抖音）
./start-web.sh          # 启动网页配置工具（默认 http://127.0.0.1:8082）
```

- `start-chrome-cdp.sh`：使用 Playwright 自带的 Chrome for Testing，监听 `9222`，登录态缓存在 `/tmp/chrome-cdp-profile`；已加载本地依赖库，无需 sudo。
- `start-web.sh`：自动准备 `uv`、Chromium 依赖等环境变量，默认端口 `8082`（可用 `PORT=xxxx` 覆盖）。
- 运行依赖位置：`uv`/`node` 在 `~/.local`，Chromium 依赖库在 `~/.local/chromium-deps`，浏览器在 `~/.cache/ms-playwright`。

## 使用说明

打开网页后：

1. 填写搜索关键词、采集数量、保存路径等参数。
2. 切换到「字段选择」Tab，勾选需要的扩展字段（如作者认证信息、播放量等）。
3. 如需更准确的认证信息，勾选「从浏览器主页提取认证信息」。
4. 如需作者级数据（粉丝数、总获赞数、IP 属地、签名等），在 Tab 底部的「作者统计（后处理）」组勾选字段（默认全选）。
5. 可选：打开「爬虫结束后自动运行作者统计后处理」开关（**默认关闭**）。建议先关闭，跑完爬虫做断点检查后，再手动补跑后处理。
6. 点击「启动爬虫」，在页面底部查看实时日志。
7. 首次运行需要扫描二维码登录抖音，后续运行会自动复用登录状态。
8. 手动运行作者统计后处理（未开自动开关时）：

   ```bash
   python3 web-config-tool/tools/enrich_author_stats.py
   ```

9. 合并导出 3 个 CSV（主表 / 评论表 / 作者表，默认产物）：

   ```bash
   python3 web-config-tool/tools/merge_douyin_outputs.py
   ```

10. 可选：生成便于阅读的单文件 3-Sheet Excel：

    ```bash
    MediaCrawler/.venv/bin/python web-config-tool/tools/build_douyin_workbook.py
    ```

## 数据合并与导出

爬虫与作者统计后处理完成后，在**项目根目录**运行（相对路径，脚本自动取最新一轮输出）。

> CSV 一个文件只能装一张表，所以 **3 张表 = 3 个 CSV 文件**（同一次运行使用同一时间戳）。需要「单个文件含 3 个 Sheet」时用下面的 Excel。

```bash
# 默认：输出 3 个 CSV（主表 / 评论表 / 作者表）
python3 web-config-tool/tools/merge_douyin_outputs.py
```

输出到 `data-outputs/douyin/merged/`：

| 文件 | 表 | 主键 | 说明 |
| --- | --- | --- | --- |
| `merged_YYYY-MM-DD_HHMMSS.csv` | 主表 | `aweme_id` | 每行一条视频，含视频字段、扩展字段、作者字段与评论聚合 |
| `comments_YYYY-MM-DD_HHMMSS.csv` | 评论表 | `comment_id` | 评论明细 |
| `authors_YYYY-MM-DD_HHMMSS.csv` | 作者表 | `sec_uid` | 作者级统计 |

主表追加的评论聚合列：`collected_comment_n`（实采评论数）、`comment_like_sum`（评论总赞）、`comment_like_avg`（平均赞）、`top_comment_like`（热评赞数）、`top_comment`（热评内容）、`top_comment_author`（热评作者）。

常用参数：`--no-comments` 不做评论聚合；`--main-only` 只输出主表 CSV；`--search` / `--extra` / `--author-stats` / `--comments` 手动指定输入文件。

如需单个 Excel 文件（3 个 Sheet 在同一个文件里，便于阅读），可选运行：

```bash
MediaCrawler/.venv/bin/python web-config-tool/tools/build_douyin_workbook.py
```

输出 `data-outputs/douyin/merged/douyin_data_YYYY-MM-DD_HHMMSS.xlsx`，其 Sheet 与上表的三张表一一对应。

> `merge_douyin_outputs.py` 仅用标准库，直接 `python3` 即可；`build_douyin_workbook.py` 依赖 `openpyxl`（MediaCrawler 虚拟环境已自带）。

详细说明请见 [web-config-tool/README.md](web-config-tool/README.md)，完整工作流请见 [web-config-tool/WORKFLOW.md](web-config-tool/WORKFLOW.md)。

## 注意事项

- 仅供学术研究使用，禁止商业用途。
- 请合理控制爬取频率，避免给目标平台带来负担。
- 采集结果默认保存在 `data-outputs/douyin/` 目录下。
- 所有输出文件名带运行级时间戳（`YYYY-MM-DD_HHMMSS`），每次运行生成独立文件，同一天多次运行互不覆盖；合并/导出脚本默认取最新一轮。
- 作者统计后处理从页面 React fiber 树定向提取作者数据（粉丝/获赞为精确值）；新版抖音作者页不再暴露 IP 属地，`ip_location` 列可能为空。
