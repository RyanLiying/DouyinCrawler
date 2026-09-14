# 抖音非遗数据采集工作流

本文档描述从打开网页配置工具到拿到最终 CSV/JSONL 的完整工作流。适合每次跑数据前快速检查。

## 1. 环境准备（只需一次）

> 依赖：Python 3.10+、uv、**Node.js ≥ 16**（抖音签名用 `execjs`，必须）、Chrome/Chromium。

1. 确认 `MediaCrawler` 已克隆到 `crawler/MediaCrawler/`。
2. 在 `MediaCrawler` 目录安装依赖：

   ```bash
   cd DouyinCrawler/MediaCrawler
   uv sync
   ```

3. 在 `web-config-tool` 目录安装后端依赖：

   ```bash
   cd DouyinCrawler/web-config-tool
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. 开启 Chrome 远程调试（CDP 模式）：
   - 打开 Chrome，地址栏输入 `chrome://inspect/#remote-debugging`。
   - 勾选 "Allow remote debugging for this browser instance"。
   - 看到 `Server running at: 127.0.0.1:9222` 即可。

## 2. 启动网页配置工具

```bash
cd DouyinCrawler/web-config-tool
source .venv/bin/activate
python server.py
```

浏览器打开 `http://127.0.0.1:8080/`。

> **WSL2/Linux**：可直接在项目根目录运行 `./start-web.sh`（自动设置环境、默认端口 `8082`）；CDP 浏览器用 `./start-chrome-cdp.sh` 启动（首次需在弹出的窗口登录抖音）。

## 3. 网页端配置（每次跑数据）

### 3.1 基础配置 Tab

- **平台**：抖音（默认）。
- **爬取类型**：search（关键词搜索）或 creator（指定创作者）。
- **关键词**：非遗相关，例如 `剪纸,皮影戏,非遗`。
- **最大爬取数量**：根据需求调整，测试时建议先小一点，如 20~50。
- **请求间隔**：3 秒（默认）。
- **保存格式**：推荐 `csv`。
- **保存路径**：默认 `DouyinCrawler/data-outputs`。
- **登录方式**：`qrcode`（首次扫码，后续复用登录态）。
- **CDP 模式**：建议开启，使用已有的 Chrome 浏览器和登录态。

### 3.2 字段选择 Tab

勾选需要的扩展字段，至少要包含：

- `is_verified`
- `verification_type`
- `custom_verify`
- `enterprise_verify_reason`

也推荐勾选：

- `play_count`
- `challenge_tags`
- `music_id`
- `music_title`
- `music_author`

注意：如果这里什么都不选，扩展字段模块不会启用，后续也拿不到认证信息。

### 3.3 认证提取开关

在「字段选择」Tab 底部勾选 **「从浏览器主页提取认证信息」**。

作用：当抖音 API 返回 `verification_type=0` 时，自动打开作者主页，从浏览器中读取真实认证信息（例如江寻千的 `文化自媒体` 黄 V）。

副作用：每个作者会额外打开一次抖音主页，速度变慢，但准确率更高。

## 4. 启动爬虫

点击 **「启动爬虫」**。页面底部会实时显示日志。

首次运行会弹出二维码，用抖音 App 扫描登录。登录态会缓存，后续运行通常无需重复扫码。

## 5. 获取数据

爬取结束后，数据会按 `SAVE_DATA_PATH` 输出到：

```
{SAVE_DATA_PATH}/douyin/
├── csv/
│   ├── search_contents_YYYY-MM-DD_HHMMSS.csv      # 主输出（标准字段）
│   ├── search_comments_YYYY-MM-DD_HHMMSS.csv     # 评论（如果开启）
│   └── ...
└── extra_fields/
    └── extra_fields_YYYY-MM-DD_HHMMSS.csv        # 扩展字段（认证、播放量、音乐等）
```

如果 `SAVE_DATA_OPTION` 不是 `csv`，扩展字段文件后缀为 `.jsonl`。

**命名规则**：所有输出文件名带**运行级时间戳**（`YYYY-MM-DD_HHMMSS`，精确到秒）。每次运行生成独立文件，同一天运行多次互不影响——既不覆盖也不混入。合并脚本、作者统计后处理都按文件修改时间自动取最新一轮。

注意：合并脚本默认只合并**最新一轮**的数据（以前按天命名的文件会累积全天）。如需合并历史某一轮，用 `--search` / `--extra` / `--author-stats` / `--comments` 手动指定对应文件。

各文件通过 `aweme_id` / `sec_uid` 关联。已提供自动合并脚本（**默认输出 CSV**）：

```bash
cd DouyinCrawler
python3 web-config-tool/tools/merge_douyin_outputs.py
```

默认会自动查找 `csv/`、`extra_fields/`、`author_stats/` 与 `csv/search_comments_*` 下最新的文件，并在 `data-outputs/douyin/merged/` 下输出 **3 个 CSV**（CSV 一个文件只能装一张表）：

| 文件 | 表 | 主键 |
| --- | --- | --- |
| `merged_YYYY-MM-DD_HHMMSS.csv` | 主表 | `aweme_id` |
| `comments_YYYY-MM-DD_HHMMSS.csv` | 评论表 | `comment_id` |
| `authors_YYYY-MM-DD_HHMMSS.csv` | 作者表 | `sec_uid` |

主表合并内容：

- 按 `aweme_id` 左连接扩展字段；
- 按 `sec_uid`（经 `author_map`）左连接作者统计，列名带 `author_` 前缀；
- 按 `aweme_id` 聚合评论，追加评论聚合列；
- 时间戳列自动转成可读日期。

评论聚合列：`collected_comment_n`（实采评论数）、`comment_like_sum`（评论总赞）、`comment_like_avg`（平均赞）、`top_comment_like`（热评赞数）、`top_comment`（热评内容）、`top_comment_author`（热评作者）。不需要评论聚合时加 `--no-comments`；只输出主表加 `--main-only`。

也可以手动指定文件：

```bash
python3 web-config-tool/tools/merge_douyin_outputs.py \
  --search data-outputs/douyin/csv/search_contents_2026-07-18.csv \
  --extra data-outputs/douyin/extra_fields/extra_fields_2026-07-18.csv \
  --output data-outputs/douyin/merged/my_merged.csv
```

如果你想用 pandas 手动合并：

```python
import pandas as pd

main = pd.read_csv("data-outputs/douyin/csv/search_contents_2026-07-18.csv")
extra = pd.read_csv("data-outputs/douyin/extra_fields/extra_fields_2026-07-18.csv")
merged = main.merge(extra, on="aweme_id", how="left")
```

## 6. 作者统计后处理（可选）

视频爬取结果不变的前提下，如需作者级数据（UID、签名、IP 属地、粉丝数、总获赞数、认证信息等），运行独立脚本 `enrich_author_stats.py`：

```bash
cd DouyinCrawler
python3 web-config-tool/tools/enrich_author_stats.py
```

脚本会：

1. 读取最新的 `search_contents`（csv / jsonl 均可，也可用 `--search` 指定）。
2. 解析作者的 `sec_uid`：若 search_contents 含 `sec_uid` 列则直接取用；否则逐条访问视频页，从主视频信息区的作者链接解析（新版页面无 SSR 全局变量，旧版 SSR 数据路径保留为兜底）。
3. 按 `sec_uid` 去重后逐个访问作者主页 `https://www.douyin.com/user/{sec_uid}`，按目标 sec_uid 从 React fiber 树定向提取用户节点（`extraction_source=fiber`，数值为精确值），失败时用 innerText 按行解析「获赞」「粉丝」「认证徽章」兜底（自动处理 `1.2w`、`3.4万` 等缩写，数值为缩写展开后的约数）。旧版页面的 SSR 全局变量路径仍保留。页面数据渐进注水，提取带轮询重试（最多约 8 秒）。
4. 输出到 `{SAVE_DATA_PATH}/douyin/author_stats/`：
   - `author_stats_YYYY-MM-DD_HHMMSS.{csv|jsonl}`：作者级数据（含 `extraction_source` 与东八区 `extract_ts_date`）。
   - `author_map_YYYY-MM-DD_HHMMSS.{csv|jsonl}`：`aweme_id -> sec_uid` 映射，供合并脚本连接。

### 字段选择

作者字段可在网页「字段选择」Tab 底部的 **「作者统计（后处理）」** 组中勾选（默认全选）。点击「启动爬虫」时，选择会保存到 `web-config-tool/author_stats_fields.json`（格式 `{"selected": [...]}`），`enrich_author_stats.py` 运行时默认读取该文件决定输出哪些列。

- `sec_uid`、`extraction_source`、`extract_ts`、`extract_ts_date` 为固定必出列，不可取消。
- 提取逻辑不受勾选影响（作者主页都打开了，全部字段顺手提取，无额外成本），勾选只过滤**输出列**；合并脚本也只会合并 author_stats 文件中实际存在的列。
- 命令行可覆盖配置文件：`--fields uid,follower_count` 只输出指定字段（优先级最高）；`--all` 忽略配置文件、输出全部可选字段。
- 配置文件不存在时默认全选。

### 自动运行开关（可选）

「作者统计（后处理）」组内有一个开关：**「爬虫结束后自动运行作者统计后处理」**，**默认关闭**。

- 勾选后：爬虫进程退出码为 0 时，后端自动用当前 Python 环境运行 `enrich_author_stats.py`，输出实时显示在页面底部日志区（与爬虫日志同一位置）；爬虫异常退出（非 0）则跳过并在日志里说明。
- 后处理失败不影响已爬取的视频数据，只在日志中打印警告和退出码。
- 依赖保护：自动运行前会检查当前环境能否 import playwright；未安装时日志会提示 `pip install playwright && playwright install chromium`（或直接改用 MediaCrawler 的 uv 环境手动跑），并跳过自动运行而不会报错崩溃。
- 不勾选时仍可在爬虫结束后手动运行脚本（推荐先做断点检查再补跑）：

```bash
python3 web-config-tool/tools/enrich_author_stats.py
```

常用参数：

```bash
python3 web-config-tool/tools/enrich_author_stats.py \
  --search data-outputs/douyin/csv/search_contents_2026-07-18.csv \
  --format csv \
  --sleep 3 \
  --cdp-port 9222 \
  --fields uid,follower_count,total_favorited
```

- 浏览器模式与爬虫一致：默认优先 CDP 连接已开启远程调试的 Chrome（复用登录态）；失败自动降级到标准 Playwright（复用 `MediaCrawler/browser_data/douyin_user_data_dir` 登录态缓存）。`--no-cdp` 可强制标准模式。
- `--sleep` 默认 3 秒（对应 `CRAWLER_MAX_SLEEP_SEC` 的含义），单个作者失败不会中断整体，结尾会打印成功/失败统计。
- 调试时可用 `--max-authors N` 限制处理的作者数。

### 与合并脚本的衔接

生成 `author_stats` 后，再运行合并脚本即可把作者字段左连接进最终统计表（新增列带 `author_` 前缀，如 `author_follower_count`、`author_total_favorited`、`author_signature`、`author_ip_location`）：

```bash
python3 web-config-tool/tools/merge_douyin_outputs.py
```

合并脚本会自动查找 `author_stats/` 下最新的 `author_stats_*` 与 `author_map_*` 文件；也可用 `--author-stats` / `--author-map` 手动指定。没有 `author_stats` 文件时行为与旧版完全一致，仅打印一行提示；`--no-author` 可强制跳过。

### 导出为 Excel（可选）

默认产物是 3 个 CSV（主表 / 评论表 / 作者表）。如需把 3 张表放进单个 Excel 文件（便于阅读），在项目根目录运行：

```bash
MediaCrawler/.venv/bin/python web-config-tool/tools/build_douyin_workbook.py
```

输出 `data-outputs/douyin/merged/douyin_data_YYYY-MM-DD_HHMMSS.xlsx`：

| Sheet | 主键 | 说明 |
| --- | --- | --- |
| 主表 | `aweme_id` | 视频信息 + 扩展字段 + 作者信息 + 评论聚合 |
| 评论表 | `comment_id` | 评论明细 |
| 作者表 | `sec_uid` | 作者级统计 |

该脚本复用合并逻辑、自动取最新一轮文件，不会重复产生评论聚合列。

## 7. 验证认证字段

重点检查 `is_verified` 和 `verification_type`：

| 字段 | 含义 |
|---|---|
| `is_verified` = 1 | 已认证 |
| `verification_type` = 1 | 个人/黄 V 认证 |
| `verification_type` = 2 | 企业/蓝 V 认证 |
| `custom_verify` | 认证理由，例如 `文化自媒体`、`传统文化创作者、乡村守护人` |
| `enterprise_verify_reason` | 企业认证说明 |

如果关闭「从浏览器主页提取认证信息」，同一个作者在不同页/关键词之间可能出现 `verification_type` 不一致。建议开启。

作者级认证字段（`author_verification_type`、`author_custom_verify` 等）见第 6 节的作者统计后处理。

## 8. 常见问题

**Q: 点击启动后没有日志**
A: 检查 `MediaCrawler` 的 `uv sync` 是否完成；检查 Chrome 远程调试是否已开启；检查 `8080` 端口是否被占用。

**Q: 认证字段全为 0**
A: 确认「字段选择」里勾选了认证相关字段；确认勾选了「从浏览器主页提取认证信息」；检查日志中是否有 `get_user_verification_from_web` 相关输出。

**Q: 扩展字段文件没生成**
A: 确认「字段选择」里至少选了一个字段；只有选了扩展字段，`run_crawler_enriched.py` 才会被调用。

**Q: 爬虫被风控/验证码**
A: 增大 `CRAWLER_MAX_SLEEP_SEC`；减少 `CRAWLER_MAX_NOTES_COUNT`；确保使用 CDP 模式连接真实 Chrome；必要时换账号或 IP 代理。

**Q: 作者统计后处理时 sec_uid 解析失败**
A: 当前 `search_contents` 不含原始 `sec_uid`（只有 `creator_hash` 匿名哈希），脚本需要访问视频页解析。确认浏览器已登录抖音；失败率高的视频可能是已删除作品，属正常情况，对应作者不会进入作者统计。

## 9. 命令行替代方式

如果不想用网页工具，可以手动生成配置后运行：

```bash
cd DouyinCrawler/MediaCrawler

# 1. 编辑或复制 base_config.py 和 dy_config.py 到 MediaCrawler/config/
# 2. 确保配置中包含：
#    SELECTED_EXTRA_FIELDS = ['is_verified', 'verification_type', 'custom_verify', 'enterprise_verify_reason']
#    USE_WEB_AUTHOR_VERIFICATION = True

# 3. 运行
uv run --active DouyinCrawler/web-config-tool/extensions/run_crawler_enriched.py
```
