# 抖音扩展字段采集说明

本目录下的文件用于**在不修改 MediaCrawler 源码**的前提下，为抖音爬取增加扩展字段采集。

## 文件说明

| 文件 | 作用 |
|---|---|
| `douyin_extra_fields.py` | 扩展字段提取逻辑 + 运行时 monkey-patch |
| `run_crawler_enriched.py` | 包装器脚本：先加载配置，再 patch，最后运行 MediaCrawler `main.py` |

## 可选字段

用户可在网页「字段选择」Tab 中自由勾选，每个字段都有中文说明：

| 字段 | 含义 |
|---|---|
| `is_verified` | 账号是否认证 |
| `verification_type` | 认证类型 |
| `enterprise_verify_reason` | 企业认证说明 |
| `is_enterprise_vip` | 是否企业号 |
| `is_gov_media_vip` | 是否政务号 |
| `music_id` | 音乐 ID |
| `music_title` | 音乐名称 |
| `music_author` | 音乐作者 |
| `play_count` | 播放量 |
| `challenge_tags` | 话题/挑战标签 |
| `is_ads` | 是否广告 |
| `has_anchor` | 是否含商业锚点 |

## 使用方法

### 1. 通过 web 工具启动（推荐）

- 打开页面后，切换到 **「字段选择」** Tab
- 勾选需要的字段（默认全选）
- 回到 **「基础配置」** 调整关键词、数量等
- 点击 **「启动爬虫」**

### 2. 命令行手动启动

```bash
cd /path/to/MediaCrawler
# 确保 config/ 目录下已放入生成好的配置（含 SELECTED_EXTRA_FIELDS = [...]）
uv run --active /path/to/web-config-tool/extensions/run_crawler_enriched.py
```

### 3. 获取扩展字段数据

爬取结束后，扩展字段保存在：

```
MediaCrawler/data/douyin/extra_fields/extra_fields_YYYY-MM-DD_HHMMSS.csv  # 主格式为 csv 时
MediaCrawler/data/douyin/extra_fields/extra_fields_YYYY-MM-DD_HHMMSS.jsonl # 主格式非 csv 时
```

通过 `aweme_id` 与主输出文件（如 `search_contents_YYYY-MM-DD_HHMMSS.jsonl`）关联即可。

## 设计原则

- **不修改 MediaCrawler 源码**：通过运行时 monkey-patch 注入，MediaCrawler 升级后可继续复用。
- **原有输出不变**：扩展字段写入独立 JSONL，避免破坏原有 CSV/JSONL/DB 输出格式。
- **用户级字段的采集决策（已更新）**：早期版本不采集 UID、粉丝数、签名、IP 属地等可能定位个人的信息；现根据研究需要，项目会通过 `tools/enrich_author_stats.py` 作者统计后处理流程采集 UID、粉丝数、签名、IP 属地等用户级字段（单独输出到 `author_stats/`，不混入视频主输出）。这些数据仅供学术研究使用，使用者需自行确保合规（如脱敏发布、遵守平台条款与相关法律法规）。
