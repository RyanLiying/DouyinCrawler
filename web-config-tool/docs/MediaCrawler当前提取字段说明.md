# MediaCrawler 抖音模块当前提取字段完整说明

> 本表基于当前实际输出整理，包含：
> - 标准输出 `search_contents_*.csv` 中的 18 个字段
> - 扩展字段输出 `extra_fields_*.csv` 中的 12 个可选字段
> - 所有枚举/类型字段的取值说明与示例
> - 时间戳转换示例

---

## 一、作品（视频/图文）标准字段

标准字段由 `MediaCrawler/store/douyin/__init__.py` 提取，不开启扩展字段时也会输出。

| 字段名 | 中文含义 | 数据类型 | 示例 | 说明 |
|---|---|---|---|---|
| `aweme_id` | 作品 ID | 字符串 | `7463777411247754559` | 抖音唯一作品标识，可与 `extra_fields` 通过该字段 join |
| `aweme_type` | 作品类型 | 字符串 | `0` | 抖音内部类型码。常见值：`0`、`4`、`55` 一般为短视频；`2` 一般为图集；`68` 一般为图文。详见下方枚举表 |
| `title` | 标题 | 字符串 | `龙泉青瓷传统烧制#非遗守护人...` | 与 `desc` 取值相同，即作品描述/文案 |
| `desc` | 作品描述 | 字符串 | `龙泉青瓷传统烧制#非遗守护人...` | 原始文案，包含话题标签文本 |
| `create_time` | 发布时间 | 整数（Unix 秒） | `1737811800` | 不是日期字符串，而是 Unix 时间戳（秒）。详见第四节转换示例 |
| `creator_hash` | 创作者匿名哈希 | 字符串 | `678d41c171b67d92` | 由 `author.uid` 经 `anonymize_user_id` 哈希生成，不可反查 |
| `nickname` | 创作者昵称（脱敏） | 字符串 | `山*` 或 `江***）` | 经 `mask_nickname` 脱敏，最后一位或几位隐藏 |
| `liked_count` | 点赞数 | 字符串 | `9672795` | 对应 `statistics.digg_count` |
| `collected_count` | 收藏数 | 字符串 | `800620` | 对应 `statistics.collect_count` |
| `comment_count` | 评论数 | 字符串 | `381034` | 对应 `statistics.comment_count` |
| `share_count` | 分享数 | 字符串 | `1593138` | 对应 `statistics.share_count` |
| `last_modify_ts` | 最后修改时间 | 整数（毫秒） | `1784345835719` | 程序生成，当前毫秒时间戳 |
| `aweme_url` | 作品链接 | 字符串 | `https://www.douyin.com/video/7463777411247754559` | 由 `aweme_id` 拼接 |
| `cover_url` | 封面图 URL | 字符串 | `https://p9-pc-sign.douyinpic.com/obj/...` | 取 `video.raw_cover` / `video.origin_cover` 的 `url_list` 中第二个 URL |
| `video_download_url` | 视频下载 URL | 字符串 | `https://www.douyin.com/aweme/v1/play/...` | 取 `video.play_addr` 相关地址的最后一个 URL |
| `music_download_url` | 音乐下载 URL | 字符串 | `https://lf26-cdn-tos.douyinstatic.com/obj/ies-music/...` | 取 `music.play_url.uri` |
| `note_download_url` | 图文笔记图片 URL | 字符串 | `url1,url2,url3` | 图集/图文作品时，多张图片 URL 用逗号分隔；短视频为空 |
| `source_keyword` | 来源搜索关键词 | 字符串 | `非遗` | 当前搜索任务使用的关键词 |

---

## 二、扩展字段

扩展字段由 `web-config-tool/extensions/douyin_extra_fields.py` 提取，仅当 `SELECTED_EXTRA_FIELDS` 非空时输出到 `extra_fields_*.csv`。

| 字段名 | 中文含义 | 数据类型 | 示例 | 说明 |
|---|---|---|---|---|
| `aweme_id` | 作品 ID | 字符串 | `7463777411247754559` | 关联字段，与 `search_contents` 中的 `aweme_id` 对应 |
| `is_verified` | 账号是否认证 | 整数（0/1） | `1` | `0` = 未认证，`1` = 已认证。若 `verification_type` 或 `custom_verify` 非空，也会推导为 `1` |
| `verification_type` | 认证类型 | 整数（0/1/2）或空 | `1` | `0` 或空 = 未认证；`1` = 个人/黄 V 认证；`2` = 企业/蓝 V 认证。详见枚举表 |
| `enterprise_verify_reason` | 企业认证说明 | 字符串 | `北京字节跳动科技有限公司` | 蓝 V 账号的企业认证名称；普通账号为空 |
| `is_enterprise_vip` | 是否企业号 | 整数（0/1） | `0` | `0` = 不是企业号，`1` = 是企业号 |
| `is_gov_media_vip` | 是否政务号 | 整数（0/1） | `0` | `0` = 不是政务/媒体号，`1` = 是政务/媒体号 |
| `music_id` | 音乐 ID | 字符串 | `7463778663067175738` | 作品使用音乐的 ID |
| `music_title` | 音乐名称 | 字符串 | `@山白创作的原声` | 作品使用音乐的标题 |
| `music_author` | 音乐作者 | 字符串 | `山白` | 作品使用音乐的作者 |
| `play_count` | 播放量 | 字符串 | `0` | 抖音 Web API 通常返回 `0`，仅作占位 |
| `challenge_tags` | 话题/挑战标签 | 字符串 | `非遗守护人,百young非遗,乡村守护人` | 多个话题标签用逗号分隔 |
| `is_ads` | 是否广告 | 整数（0/1） | `0` | `0` = 非广告内容，`1` = 广告/推广内容 |
| `has_anchor` | 是否含商业锚点 | 整数（0/1） | `0` | `0` = 无商业锚点，`1` = 含商品/POI 等锚点 |
| `extra_extract_ts` | 扩展字段提取时间 | 整数（毫秒） | `1721289600000` | 程序生成，当前毫秒时间戳 |

---

## 三、枚举/类型字段取值速查表

### 3.1 `aweme_type`（作品类型）

| 取值 | 含义 | 示例场景 |
|---|---|---|
| `0` | 短视频（最常见） | 普通竖屏/横屏视频 |
| `4` | 短视频 | 部分竖屏视频 |
| `55` | 短视频 | 抖音精选/长视频等 |
| `2` | 图集 | 多张图片滑动浏览 |
| `68` | 图文 | 图文笔记形式 |

> 注意：抖音内部类型码可能随版本调整，上表基于当前观察整理。若遇到未列出的值，可直接按 `aweme_type` 原值保存，不影响后续分析。

### 3.2 `is_verified`（是否认证）

| 取值 | 含义 |
|---|---|
| `0` | 未认证 |
| `1` | 已认证（个人黄 V 或企业蓝 V） |

### 3.3 `verification_type`（认证类型）

| 取值 | 含义 | 说明 |
|---|---|---|
| `0` 或空 | 未认证 | 未认证账号，或扩展字段未启用 |
| `1` | 个人/黄 V 认证 | 如 `文化自媒体`、`传统文化创作者、乡村守护人` |
| `2` | 企业/蓝 V 认证 | 如 `北京字节跳动科技有限公司` |

> 注意：若未开启「从浏览器主页提取认证信息」，部分真实黄 V 账号会被 API 误判为 `0`。建议开启该开关。

### 3.4 `is_enterprise_vip`（是否企业号）

| 取值 | 含义 |
|---|---|
| `0` | 不是企业号 |
| `1` | 是企业号 |

### 3.5 `is_gov_media_vip`（是否政务/媒体号）

| 取值 | 含义 |
|---|---|
| `0` | 不是政务/媒体号 |
| `1` | 是政务/媒体号 |

### 3.6 `is_ads`（是否广告）

| 取值 | 含义 |
|---|---|
| `0` | 非广告内容 |
| `1` | 广告或推广内容 |

### 3.7 `has_anchor`（是否含商业锚点）

| 取值 | 含义 |
|---|---|
| `0` | 无商业锚点 |
| `1` | 包含商品链接、POI 地点等商业锚点 |

---

## 四、时间戳字段转换说明

`create_time` 是 **Unix 时间戳（秒）**，不是可读的日期字符串。转换方法如下：

### Python 示例

```python
from datetime import datetime
import pandas as pd

df = pd.read_csv("data-outputs/douyin/csv/search_contents_2026-07-18.csv")

# 转成北京时间
beijing_offset = 8 * 3600
df["publish_dt"] = pd.to_datetime(df["create_time"] + beijing_offset, unit="s", utc=True).dt.tz_convert("Asia/Shanghai")

# 仅保留日期字符串
publish_date = df["publish_dt"].dt.strftime("%Y-%m-%d %H:%M:%S")
```

### Excel / WPS 示例

在空白列输入公式：

```excel
=(A2 + 8*3600) / 86400 + DATE(1970, 1, 1)
```

然后将单元格格式设为 `yyyy-mm-dd hh:mm:ss`。

> `last_modify_ts` 和 `extra_extract_ts` 是毫秒时间戳，转换时 `unit="ms"`。

---

## 五、合并与导出

标准字段、扩展字段、作者统计、评论是分开存储的，需要按 `aweme_id` / `sec_uid` 合并。可使用已提供的脚本（在项目根目录运行）：

```bash
python3 web-config-tool/tools/merge_douyin_outputs.py
```

默认在 `data-outputs/douyin/merged/` 输出 3 个 CSV（CSV 一个文件只能装一张表）：

| 文件 | 表 | 主键 |
| --- | --- | --- |
| `merged_YYYY-MM-DD_HHMMSS.csv` | 主表 | `aweme_id` |
| `comments_YYYY-MM-DD_HHMMSS.csv` | 评论表 | `comment_id` |
| `authors_YYYY-MM-DD_HHMMSS.csv` | 作者表 | `sec_uid` |

主表列 = 标准字段（18）+ 扩展字段（12，以实际勾选为准）+ 作者字段（`author_` 前缀）+ 评论聚合列，另含时间戳转换出的可读日期列。评论聚合列：`collected_comment_n`、`comment_like_sum`、`comment_like_avg`、`top_comment_like`、`top_comment`、`top_comment_author`。

输出示例：

```text
合并完成：data-outputs/douyin/merged/merged_2026-09-14_133513.csv
总记录数：231，成功匹配扩展字段：231，未匹配：0
成功匹配作者统计：227，未匹配：4
成功匹配评论聚合：231，未匹配：0
评论表：data-outputs/douyin/merged/comments_2026-09-14_133513.csv
作者表：data-outputs/douyin/merged/authors_2026-09-14_133513.csv
```

如需把 3 张表放进单个 Excel 文件（3 个 Sheet），可选运行：

```bash
MediaCrawler/.venv/bin/python web-config-tool/tools/build_douyin_workbook.py
```

---

## 六、明确未提取的接口可用字段

以下字段抖音接口通常会返回，但当前代码未保存：

- `author.uid`、`author.avatar_thumb`、`author.signature`、`author.follower_count`、`ip_label`：涉及用户身份、头像、签名、粉丝数、IP 归属地 —— 教学版故意不保存，防止定位个人。
- `text_extra`：原始话题文本偏移信息。
- `commerce_info`：更详细的商业信息。

如需新增字段，需要同步修改：

1. `MediaCrawler/store/douyin/__init__.py` 中的提取逻辑
2. `MediaCrawler/database/models.py` 中的 `DouyinAweme` 表结构
3. 扩展字段相关代码（若属于扩展字段）
4. 本说明文档

