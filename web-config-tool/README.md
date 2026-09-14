# MediaCrawler 网页配置与运行工具

一个面向抖音非遗研究的网页版配置工具。支持可视化配置 MediaCrawler 参数，并在页面中直接启动爬虫，无需覆盖原配置文件。

## 功能

- 中文可视化配置所有 MediaCrawler 参数
- 实时预览生成的 `base_config.py` 和 `dy_config.py`
- 一键下载配置文件，或直接在页面中启动爬虫
- 启动爬虫时不覆盖 `MediaCrawler/config/` 源文件，后端会生成临时配置目录
- 通过 SSE 实时显示爬虫运行日志

## 项目结构

```
crawler/
├── MediaCrawler/              # MediaCrawler 官方仓库
└── web-config-tool/
    ├── index.html             # 前端页面（中文）
    ├── server.py              # Flask 后端服务
    ├── requirements.txt       # Python 依赖
    ├── tools/
    │   ├── enrich_author_stats.py    # 作者统计后处理
    │   ├── merge_douyin_outputs.py   # 合并导出 3 个 CSV（主表/评论表/作者表）
    │   └── build_douyin_workbook.py  # 生成 3-Sheet Excel（主表/评论表/作者表）
    └── README.md              # 本文件
```

## 环境准备

1. 确保已安装 Python 3.10+ 和 uv。
2. 确保已安装 Node.js ≥ 16（抖音签名用 `execjs`，必须）。
3. 创建并激活虚拟环境，安装后端依赖：

```bash
cd DouyinCrawler/web-config-tool
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 启动方式

> WSL2/Linux 用户可直接在项目根目录运行 `./start-web.sh`：它会自动准备好 `uv`、Chromium 依赖等环境变量，默认端口 `8082`；CDP 浏览器用 `./start-chrome-cdp.sh` 启动。

### 1. 启动后端服务

```bash
cd DouyinCrawler/web-config-tool
source .venv/bin/activate
python server.py
```

服务默认运行在 `http://127.0.0.1:8080`。如果 8080 被占用，可以换端口：

```bash
PORT=8081 python server.py
```

然后访问 `http://127.0.0.1:8081/`。

### 2. 打开前端页面

推荐通过后端访问，避免本地文件协议的 CORS 问题：

```
http://127.0.0.1:8080/
```

也可以直接双击 `index.html` 打开（现代浏览器通常允许本地页面访问 `localhost`）。

## 使用步骤

1. 打开页面后，填写爬虫参数。默认已填好非遗关键词。
2. 查看右侧实时预览的配置文件。
3. 如需手动下载配置，点击「下载 base_config.py」或「下载 dy_config.py」。
4. 切换到 **「字段选择」** Tab，勾选需要的扩展字段（如 `is_verified`、`verification_type`、`play_count` 等）。
5. 如需更准确的作者认证信息，勾选 **「从浏览器主页提取认证信息」**。
6. 如需作者级数据，在 Tab 底部的 **「作者统计（后处理）」** 组勾选字段（默认全选），详见下文。
7. 点击 **「启动爬虫」**。
8. 页面底部会实时显示运行日志。
9. 如需停止，点击「停止爬虫」。

完整工作流参考 [WORKFLOW.md](WORKFLOW.md)。

## 作者统计（后处理）

在视频爬取结果不变的前提下，额外产出作者级数据：先爬视频 → 按作者去重 → 统一访问作者主页提取（UID、签名、IP 属地、粉丝数、总获赞数、认证信息等）→ 与主输出并表。

### 字段勾选

「字段选择」Tab 底部的 **「作者统计（后处理）」** 组（默认全选）。点击「启动爬虫」时选择保存到 `author_stats_fields.json`（格式 `{"selected": [...]}`），后处理脚本运行时默认读取它决定输出列。`sec_uid`、`extraction_source`、`extract_ts`、`extract_ts_date` 为固定必出列。

### 自动运行开关

「作者统计（后处理）」组内的 **「爬虫结束后自动运行作者统计后处理」** 开关，**默认关闭**。

- 勾选后：爬虫退出码为 0 且本次爬到了视频数据时，后端自动运行后处理，日志与爬虫日志显示在同一位置；本次 0 条数据或爬虫异常退出时自动跳过。
- 后处理失败不影响已爬取的视频数据，只在日志里打印警告和退出码。
- 建议：先保持关闭，爬虫结束后做断点检查，确认数据正常再手动补跑。

### 手动运行

```bash
cd DouyinCrawler
python3 web-config-tool/tools/enrich_author_stats.py
```

### 提取策略与已知限制

- 作者页数据从页面的 React fiber 树按目标 `sec_uid` 定向提取（`extraction_source=fiber`，粉丝/获赞为精确值）；失败时降级 innerText 行解析（缩写展开为约数）。页面数据渐进注水，提取自带轮询重试。
- 视频页 `sec_uid` 从主视频信息区的作者链接解析（排除相关推荐/评论区链接）。
- **已知限制**：新版抖音作者页不再暴露 IP 属地，`ip_location` 列大概率为空；`uid` 列为数字内部 ID，抖音号（如 `pnk0518`）目前不单独输出。

### 输出位置

所有输出文件名带运行级时间戳（`YYYY-MM-DD_HHMMSS`），每次运行生成独立文件，同一天多次运行互不覆盖；合并/后处理脚本自动取最新一轮。

输出到 `{SAVE_DATA_PATH}/douyin/author_stats/`：

- `author_stats_YYYY-MM-DD_HHMMSS.{csv|jsonl}`：作者级数据。
- `author_map_YYYY-MM-DD_HHMMSS.{csv|jsonl}`：`aweme_id -> sec_uid` 映射，供合并脚本连接。

最后运行合并脚本：把作者字段（带 `author_` 前缀）与评论聚合左连接进主表，并导出 3 个 CSV。CSV 一个文件只能装一张表，故 3 张表 = 3 个文件（同一次运行使用同一时间戳）：

```bash
# 在项目根目录运行
python3 web-config-tool/tools/merge_douyin_outputs.py
```

输出到 `data-outputs/douyin/merged/`：

| 文件 | 表 | 主键 |
| --- | --- | --- |
| `merged_YYYY-MM-DD_HHMMSS.csv` | 主表 | `aweme_id` |
| `comments_YYYY-MM-DD_HHMMSS.csv` | 评论表 | `comment_id` |
| `authors_YYYY-MM-DD_HHMMSS.csv` | 作者表 | `sec_uid` |

主表追加的评论聚合列：`collected_comment_n`（实采评论数）、`comment_like_sum`（评论总赞）、`comment_like_avg`（平均赞）、`top_comment_like`（热评赞数）、`top_comment`（热评内容）、`top_comment_author`（热评作者）。`--no-comments` 可跳过评论聚合，`--main-only` 只输出主表。

### 生成 3-Sheet Excel（可选）

如需把 3 张表放进单个 Excel 文件（便于阅读），在项目根目录运行（依赖 openpyxl，MediaCrawler 虚拟环境已自带）：

```bash
MediaCrawler/.venv/bin/python web-config-tool/tools/build_douyin_workbook.py
```

输出 `data-outputs/douyin/merged/douyin_data_YYYY-MM-DD_HHMMSS.xlsx`，Sheet 与上表三张表一一对应。

### 登录墙检测与熔断

- 后处理访问页面时做登录墙检测（登录 URL 重定向、「扫码登录」等文案、二维码弹窗 DOM）。命中即中断运行并打印醒目的重新登录指引（标准模式：删除 `MediaCrawler/browser_data/douyin_user_data_dir` 后重新扫码；CDP 模式：在调试实例里手动登录），已提取的部分数据仍会写盘，进程以非 0 退出码结束。
- 视频页 `sec_uid` 解析连续失败 3 次会自动熔断中断（疑似页面结构变化或触发风控），避免空转。

### 停止按钮可中断

后处理子进程与爬虫共用同一套停止机制，自动运行时点击「停止爬虫」可直接终止后处理。

更完整的说明见 [WORKFLOW.md](WORKFLOW.md) 第 6 节。

## 首次运行前的重要准备

### 1. 在 MediaCrawler 目录安装依赖

```bash
cd DouyinCrawler/MediaCrawler
uv sync
```

### 2. 配置 Chrome 远程调试（CDP 模式）

日常使用的 Chrome **不用动**。用命令行单独启动一个调试专用实例（独立用户数据目录，与日常 Chrome 互不影响）：

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-cdp-profile \
  --no-first-run
```

- 首次需在这个调试实例里手动登录抖音（登录态缓存在 `/tmp/chrome-cdp-profile`，后续复用（/tmp 会随系统重启清空，重启 Mac 后需重新登录一次））。
- 验证：`curl http://localhost:9222/json/version`，返回 JSON 即正常。
- 旧的 `chrome://inspect` 勾选方式要求完全退出日常 Chrome 才能生效，不推荐。

### 3. 二维码登录

- 首次启动爬虫时会弹出二维码，用抖音 App 扫描登录。
- 登录态会被缓存，后续运行通常无需重复登录。

## 注意事项

- 本工具仅供学术研究使用，禁止商业用途。
- 请合理控制爬取频率，避免给目标平台带来负担。
- 临时配置文件存放在 `/tmp/mediacrawler_config_xxx/` 目录下，运行结束后不会自动删除，可手动清理。
- 如果遇到风控或验证码，可适当增大「请求间隔」、减少「最大爬取数量」，或使用 CDP 模式连接真实浏览器。

## 常见问题

**Q: 页面提示「网络请求失败」**
A: 请确认后端服务已启动（`python server.py`）。

**Q: 点击「启动爬虫」后没有日志**
A: 检查 MediaCrawler 依赖是否已安装（`uv sync`），以及 Chrome 远程调试是否已开启。如果勾选了扩展字段，确认 `web-config-tool/extensions/run_crawler_enriched.py` 路径正确。

**Q: 为什么认证字段全是 0？**
A: 确认已勾选扩展字段中的 `is_verified`/`verification_type`；并勾选「从浏览器主页提取认证信息」。只有开启后者，才能修正 API 返回 `verification_type=0` 但实际有黄 V 的账号（如江寻千）。

**Q: CDP 连接失败或返回 404**
A: 先 `curl http://localhost:9222/json/version` 确认调试服务存在。常见原因是用 `chrome://inspect` 方式开启调试但没有完全退出日常 Chrome（该方式要求所有 Chrome 进程退出后重开才生效）。推荐改用命令行启动调试专用实例（见上文「配置 Chrome 远程调试」），与日常 Chrome 互不干扰。另：新版 Chrome 可能只把 9222 绑在 IPv6 `[::1]` 上，爬虫和后处理脚本已内置兼容（IPv4/IPv6 都会试），请勿自行改回只连 `127.0.0.1` 的旧版本。

**Q: 爬虫结束后调试专用的 Chrome 被关掉了**
A: 该问题已修复：CDP 连接已有浏览器时，爬虫退出只断开连接，不再关闭浏览器。请确保 MediaCrawler 为最新代码。

**Q: 后处理时视频页反复弹出登录二维码、页面不停开关**
A: 该问题已修复。`enrich_author_stats.py` 现在带有登录墙检测：命中登录页重定向、登录文案或二维码弹窗时，会立即中断运行并在日志中打印重新登录指引（标准模式删除 `MediaCrawler/browser_data/douyin_user_data_dir` 重新扫码；CDP 模式在调试实例里手动登录抖音），不再空转。另外连续 3 次解析失败也会自动熔断。

**Q: 扩展字段数据在哪里？**
A: 扩展字段单独输出到 `{SAVE_DATA_PATH}/douyin/extra_fields/extra_fields_YYYY-MM-DD_HHMMSS.{csv|jsonl}`，通过 `aweme_id` 与主输出文件关联。详见 [WORKFLOW.md](WORKFLOW.md)。
A: 填写表单后，点击「下载 base_config.py」和「下载 dy_config.py」，然后手动复制到 `MediaCrawler/config/` 目录。

## 技术说明

后端通过 `PYTHONPATH` 环境变量将临时配置目录置顶，使 MediaCrawler 加载临时配置而不是原 `config/` 目录。这样实现了"不覆盖源文件即可运行"。
