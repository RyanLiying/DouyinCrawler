#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作者统计数据后处理：对 search_contents 中的作者去重后统一访问作者主页，
提取用户级数据（UID、签名、IP 属地、粉丝数、总获赞数、认证信息等），
输出作者级文件，供 merge_douyin_outputs.py 按 sec_uid 左连接进最终统计表。

提取策略：
1. SSR 路径（旧版页面）：page.evaluate 探查 window 的 _SSR_HYDRATED_DATA / __INITIAL_STATE__
   / __SERVER_DATA__ / __DOUYIN_USER__，递归按 sec_uid 匹配 user 节点直读字段；
2. fiber 路径（新版页面）：数据在 window.RENDER_DATA 的 React fiber 树里，按目标 sec_uid
   定向匹配用户节点（页面上同时有登录用户节点，必须精确匹配），轮询等待注水完成；
3. innerText 兜底：按行解析「获赞」「粉丝」「关注」行（处理 1.2w / 3.4万 等缩写），
   认证字段沿用「认证徽章」行逻辑作为兜底。

 浏览器模式：优先 CDP 连接用户已打开的 Chrome（默认 localhost:9222，兼容 IPv6-only 绑定），
失败则自动降级到标准 Playwright（复用 crawler 的浏览器用户数据目录以保留登录态）。

注意：当前 search_contents 行内不含原始 sec_uid（只有 creator_hash 匿名哈希），
因此脚本会先访问视频页解析出 author.sec_uid（同时输出 aweme_id -> sec_uid 映射文件），
再按作者去重访问主页。若后续 search_contents 直接带 sec_uid 列，则自动跳过解析步骤。

仅供学术研究使用，请自行确保合规。
"""

import argparse
import asyncio
import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from glob import glob
from pathlib import Path

# 与 merge_douyin_outputs.py 保持一致的默认数据根目录（从文件位置推导项目根，不硬编码绝对路径）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = str(_PROJECT_ROOT / "data-outputs")
# MediaCrawler 仓库位置（用于定位登录态缓存目录和 stealth 脚本）
DEFAULT_MEDIACRAWLER_ROOT = str(_PROJECT_ROOT / "MediaCrawler")

AUTHOR_PAGE_URL = "https://www.douyin.com/user/{sec_uid}"
VIDEO_PAGE_URL = "https://www.douyin.com/video/{aweme_id}"

# 东八区时区（与 merge 脚本的时间戳转换做法一致）
TZ_E8 = timezone(timedelta(hours=8))

# 作者级输出字段（列顺序固定）
AUTHOR_STAT_FIELDS = [
    "sec_uid",
    "uid",
    "nickname",
    "signature",
    "ip_location",
    "follower_count",
    "total_favorited",
    "following_count",
    "aweme_count",
    "is_verified",
    "verification_type",
    "custom_verify",
    "enterprise_verify_reason",
    "extraction_source",  # ssr / fiber / innertext / none
    "extract_ts",         # 秒级时间戳
    "extract_ts_date",    # 东八区可读日期
]

# 可选作者字段的中文说明（风格对齐 extensions/douyin_extra_fields.py 的 EXTRA_FIELD_DESCRIPTIONS）
# 网页「字段选择」Tab 与 author_stats_fields.json 均使用这里的字段名
AUTHOR_STAT_FIELD_DESCRIPTIONS = {
    "uid": "作者 UID",
    "nickname": "作者昵称（主页实时值）",
    "signature": "作者签名",
    "ip_location": "IP 属地",
    "follower_count": "粉丝数",
    "total_favorited": "总获赞数",
    "following_count": "关注数",
    "aweme_count": "作品数",
    "is_verified": "账号是否认证",
    "verification_type": "认证类型",
    "custom_verify": "认证说明（黄 V）",
    "enterprise_verify_reason": "企业认证说明（蓝 V）",
}

# 默认全选（未指定 --fields 且配置文件不存在时生效）
DEFAULT_SELECTED_AUTHOR_FIELDS = list(AUTHOR_STAT_FIELD_DESCRIPTIONS.keys())

# 固定必出列（不可取消）：关联键 + 提取元信息
FIXED_AUTHOR_FIELDS = ["sec_uid", "extraction_source", "extract_ts", "extract_ts_date"]

# 网页端字段选择的持久化文件（server.py 写入，本脚本默认读取）
AUTHOR_STATS_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "author_stats_fields.json"
)

# search_contents 中可能出现的 sec_uid 列名（按优先级）
SEC_UID_COLUMNS = ["sec_uid", "author_sec_uid", "author.sec_uid"]

# 探查 SSR 数据的 JS（与 client.py 一致）
SSR_PROBE_JS = """() => {
    const keys = ['_SSR_HYDRATED_DATA', '__INITIAL_STATE__', '__SERVER_DATA__', '__DOUYIN_USER__'];
    for (const key of keys) {
        if (window[key]) return {key: key, data: window[key]};
    }
    return null;
}"""

# 读取页面正文的 JS
BODY_TEXT_JS = "() => document.body ? document.body.innerText : ''"

# 视频页提取作者 sec_uid 的 JS。
# 抖音新版页面没有 SSR 全局变量（window._SSR_HYDRATED_DATA 等均为空），数据挂在
# window.RENDER_DATA 的 React fiber 树上；但直接扫 fiber 会先撞见登录用户自己的节点，
# 所以走 DOM：主作者链接位于「发布时间」所在的详情信息区内，相关推荐/评论区的链接要排除。
VIDEO_AUTHOR_JS = """() => {
    const pick = (root) => {
        const anchors = root.querySelectorAll('a[href*="/user/"]');
        for (const a of anchors) {
            const m = (a.getAttribute('href') || '').match(/MS4wLjAB[A-Za-z0-9_\\-]+/);
            if (m) return m[0];
        }
        return null;
    };
    const timeEl = document.querySelector('[data-e2e="detail-video-publish-time"]');
    if (timeEl) {
        let box = timeEl;
        for (let i = 0; i < 6 && box; i++) {
            const found = box.querySelector ? pick(box) : null;
            if (found) return found;
            box = box.parentElement;
        }
    }
    const infoBox = document.querySelector('[data-e2e="detail-video-info"]');
    if (infoBox) {
        const found = pick(infoBox);
        if (found) return found;
    }
    return null;
}"""

# 作者页从 React fiber 树按目标 sec_uid 精确提取用户节点的 JS。
# 页面上同时存在登录用户节点，必须按 URL 里的目标 sec_uid 匹配，不能取"第一个用户节点"。
# fiber 树有循环引用且体量大，用 WeakSet 去环 + 步数预算防卡死，只回传白名单字段的字符串值。
AUTHOR_FIBER_JS = """(targetSecUid) => {
    const seen = new WeakSet();
    let best = null;
    let steps = 0;
    const walk = (node, depth) => {
        if (best || depth > 30 || node === null || typeof node !== 'object') return;
        if (++steps > 200000) return;
        if (seen.has(node)) return;
        seen.add(node);
        if (!Array.isArray(node) && (node.secUid === targetSecUid || node.sec_uid === targetSecUid)) {
            best = node;
            return;
        }
        const vals = Array.isArray(node) ? node.slice(0, 100) : Object.values(node);
        for (const v of vals) walk(v, depth + 1);
    };
    walk(window.RENDER_DATA, 0);
    if (!best) return null;
    const keep = ['uid', 'secUid', 'sec_uid', 'shortId', 'uniqueId', 'unique_id', 'nickname',
        'desc', 'signature', 'ipLocation', 'ip_location', 'followerCount', 'follower_count',
        'totalFavorited', 'total_favorited', 'followingCount', 'following_count',
        'awemeCount', 'aweme_count', 'customVerify', 'custom_verify', 'enterpriseVerifyReason',
        'enterprise_verify_reason', 'verificationType', 'verification_type',
        'accountCertInfo', 'account_cert_info'];
    const out = {};
    for (const k of keep) {
        const v = best[k];
        if (v === undefined || v === null) continue;
        out[k] = (typeof v === 'object') ? JSON.stringify(v) : String(v);
    }
    return out;
}"""


async def evaluate_until(page, js: str, arg=None, attempts: int = 6, interval: float = 1.0):
    """轮询执行页面 JS 直到拿到真值结果。

    抖音新版页面的数据在 React fiber 树里渐进注水，固定 sleep 不可靠：
    2 秒时 RENDER_DATA 已存在但用户节点可能尚未挂上，5 秒时才有。
    """
    for i in range(attempts):
        result = await (page.evaluate(js, arg) if arg is not None else page.evaluate(js))
        if result:
            return result
        if i < attempts - 1:
            await asyncio.sleep(interval)
    return None


def find_latest_file(pattern: str) -> str:
    """按修改时间查找最新文件，与 merge 脚本一致。"""
    files = glob(pattern)
    if not files:
        raise FileNotFoundError(f"找不到匹配文件: {pattern}")
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[0]


def read_rows(path: str) -> list:
    """读取 search_contents 输出，按扩展名自动识别 csv / jsonl。"""
    rows = []
    if path.endswith(".jsonl"):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    else:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(dict(row))
    return rows


def write_rows(path: str, rows: list, fieldnames: list, fmt: str):
    """按指定格式写出文件，csv 使用 utf-8-sig 与项目其它输出一致。"""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    if fmt == "jsonl":
        with open(path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    else:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in fieldnames})


def ts_to_date_e8(ts: int) -> str:
    """秒级时间戳转东八区可读日期，与 merge 脚本一致。"""
    try:
        return datetime.fromtimestamp(int(ts), TZ_E8).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def resolve_selected_fields(args) -> tuple:
    """决定生效的作者字段清单，返回 (字段列表, 来源说明)。

    优先级：CLI --fields > CLI --all（忽略配置文件，默认全选）
    > web-config-tool/author_stats_fields.json > 默认全选。
    非法字段名会被忽略。
    """
    if args.fields:
        fields = [f.strip() for f in args.fields.split(",") if f.strip() in AUTHOR_STAT_FIELD_DESCRIPTIONS]
        return fields, "CLI --fields"
    if args.all_fields:
        return list(DEFAULT_SELECTED_AUTHOR_FIELDS), "CLI --all（默认全选）"
    try:
        with open(AUTHOR_STATS_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        fields = [f for f in data.get("selected", []) if f in AUTHOR_STAT_FIELD_DESCRIPTIONS]
        if fields or data.get("selected") == []:
            return fields, f"配置文件 {AUTHOR_STATS_CONFIG_PATH}"
    except FileNotFoundError:
        pass
    except Exception as exc:
        print(f"[warn] 读取字段配置 {AUTHOR_STATS_CONFIG_PATH} 失败（{exc}），使用默认全选")
    return list(DEFAULT_SELECTED_AUTHOR_FIELDS), "默认值（全选）"


def build_output_fieldnames(selected_fields: list) -> list:
    """按 AUTHOR_STAT_FIELDS 的固定顺序，生成「固定列 + 已选可选列」的输出列。"""
    selected = set(selected_fields)
    return [
        c for c in AUTHOR_STAT_FIELDS
        if c in FIXED_AUTHOR_FIELDS or c in selected
    ]


def parse_count_abbr(text) -> int:
    """把「1.2w」「3.4万」「1.5亿」「12,345」这类缩写换算为整数；无法解析返回 -1。"""
    if text is None:
        return -1
    if isinstance(text, (int, float)):
        return int(text)
    s = str(text).strip().replace(",", "")
    if not s:
        return -1
    m = re.match(r"^([\d.]+)\s*([wW万亿]?)$", s)
    if not m:
        return -1
    try:
        num = float(m.group(1))
    except ValueError:
        return -1
    unit = m.group(2)
    if unit in ("w", "W", "万"):
        num *= 10000
    elif unit == "亿":
        num *= 100000000
    return int(num)


def extract_user_from_ssr(data, sec_uid: str):
    """在 SSR 数据里递归查找 sec_uid 匹配的 user 节点（与 client.py 一致）。"""
    if isinstance(data, dict):
        if data.get("sec_uid") == sec_uid or data.get("sec_user_id") == sec_uid:
            return data
        for v in data.values():
            user = extract_user_from_ssr(v, sec_uid)
            if user:
                return user
    elif isinstance(data, list):
        for item in data:
            user = extract_user_from_ssr(item, sec_uid)
            if user:
                return user
    return None


def normalize_fiber_user(node: dict) -> dict:
    """把 fiber 节点的 camelCase 字段归一化为现有管道使用的 snake_case。

    desc 是抖音个人简介在 fiber 里的字段名，对应 API 的 signature。
    """
    def pick(*keys):
        for k in keys:
            v = node.get(k)
            if v not in (None, ""):
                return v
        return ""

    return {
        "uid": pick("uid", "uniqueId", "unique_id", "shortId"),
        "nickname": pick("nickname"),
        "signature": pick("signature", "desc"),
        "ip_location": pick("ip_location", "ipLocation"),
        "follower_count": pick("follower_count", "followerCount"),
        "total_favorited": pick("total_favorited", "totalFavorited"),
        "following_count": pick("following_count", "followingCount"),
        "aweme_count": pick("aweme_count", "awemeCount"),
        "custom_verify": pick("custom_verify", "customVerify"),
        "enterprise_verify_reason": pick("enterprise_verify_reason", "enterpriseVerifyReason"),
        "verification_type": pick("verification_type", "verificationType"),
        "account_cert_info": pick("account_cert_info", "accountCertInfo"),
    }


def find_first_sec_uid(data):
    """在 SSR 数据里递归查找第一个带 sec_uid + nickname 的节点（用于视频页解析作者）。"""
    if isinstance(data, dict):
        sec_uid = data.get("sec_uid") or data.get("sec_user_id")
        if sec_uid and data.get("nickname"):
            return str(sec_uid)
        for v in data.values():
            found = find_first_sec_uid(v)
            if found:
                return found
    elif isinstance(data, list):
        for item in data:
            found = find_first_sec_uid(item)
            if found:
                return found
    return None


def parse_cert_from_ssr(user: dict, result: dict):
    """SSR user 节点直读认证字段；没有时解析 account_cert_info（对齐 client.py 逻辑）。"""
    result["verification_type"] = user.get("verification_type", "") or ""
    result["custom_verify"] = user.get("custom_verify", "") or ""
    result["enterprise_verify_reason"] = user.get("enterprise_verify_reason", "") or ""
    is_verified = user.get("is_verified")
    result["is_verified"] = int(is_verified) if is_verified is not None else 0

    if not result["verification_type"] and not result["enterprise_verify_reason"]:
        cert_info = user.get("account_cert_info")
        if isinstance(cert_info, str):
            try:
                cert_info = json.loads(cert_info)
            except json.JSONDecodeError:
                cert_info = None
        if isinstance(cert_info, dict):
            label_text = str(cert_info.get("label_text", ""))
            label_style = cert_info.get("label_style", 0)
            is_biz = cert_info.get("is_biz_account", 0)
            if label_text or label_style or is_biz:
                result["is_verified"] = 1
                result["enterprise_verify_reason"] = label_text
                result["verification_type"] = 2 if (is_biz or label_style in (7, 8)) else 1

    # 有认证说明但 is_verified 仍为 0 时修正（对齐 douyin_extra_fields 的做法）
    if not result["is_verified"] and (
        str(result["verification_type"]) not in ("", "0")
        or result["custom_verify"]
        or result["enterprise_verify_reason"]
    ):
        result["is_verified"] = 1
    return result


def parse_innertext(body_text: str) -> dict:
    """innerText 兜底解析：按行找「获赞」「粉丝」「关注」与「认证徽章」。

    抖音主页 innerText 常见形态（label 与数字可能同行或相邻两行）：
        获赞 1.2w
        粉丝
        3.4万
    """
    result = {}
    lines = [ln.strip() for ln in body_text.split("\n") if ln.strip()]
    label_map = [("获赞", "total_favorited"), ("粉丝", "follower_count"), ("关注", "following_count")]
    for i, line in enumerate(lines):
        for label, field in label_map:
            if field in result:
                continue
            value = -1
            if line == label:
                # label 独占一行时取下一行
                if i + 1 < len(lines):
                    value = parse_count_abbr(lines[i + 1])
            elif line.startswith(label):
                value = parse_count_abbr(line[len(label):])
            if value >= 0:
                result[field] = value

    # 认证兜底：沿用「认证徽章」行逻辑（与 client.py 一致）
    for i, line in enumerate(lines):
        if line == "认证徽章":
            cert_reason = lines[i + 1] if i + 1 < len(lines) else ""
            result["is_verified"] = 1
            result["custom_verify"] = cert_reason
            badge_text = cert_reason.lower()
            if any(k in badge_text for k in ["蓝v", "企业", "官方", "机构"]):
                result["verification_type"] = 2
            else:
                result["verification_type"] = 1
            break
    return result


def empty_author_row(sec_uid: str, extract_ts: int) -> dict:
    """生成一条空记录（单个作者失败时使用，保证不中断整体流程）。"""
    row = {k: "" for k in AUTHOR_STAT_FIELDS}
    row["sec_uid"] = sec_uid
    row["is_verified"] = 0
    row["extraction_source"] = "none"
    row["extract_ts"] = extract_ts
    row["extract_ts_date"] = ts_to_date_e8(extract_ts)
    return row


class LoginWallError(Exception):
    """检测到抖音登录墙（登录态失效）时抛出，用于中断整个后处理运行，避免一路空转。"""


# 登录墙判断只使用明确信号，避免误杀正常页面：
# 正文里出现登录弹窗专属文案（普通页面顶栏只有「登录」按钮，不含这些完整词组）
LOGIN_WALL_TEXT_KEYWORDS = ["扫码登录", "登录后查看", "登录抖音"]
# URL 被重定向到登录域
LOGIN_WALL_URL_KEYWORDS = ["/login", "passport"]
# 连续解析失败熔断阈值（防止页面结构未知变化导致无限空转）
MAX_CONSECUTIVE_RESOLVE_FAILURES = 3


async def detect_login_wall(page) -> str:
    """检测页面是否被抖音登录墙拦截，返回拦截原因；空字符串表示页面正常。

    综合三类信号：URL 重定向、正文登录文案、登录二维码弹窗 DOM。
    检测本身出错时按正常处理，不误杀。
    """
    try:
        url = (page.url or "").lower()
        if any(k in url for k in LOGIN_WALL_URL_KEYWORDS):
            return f"页面被重定向到登录地址: {page.url}"
        body_text = await page.evaluate(BODY_TEXT_JS) or ""
        for kw in LOGIN_WALL_TEXT_KEYWORDS:
            if kw in body_text:
                return f"页面出现登录提示文案「{kw}」"
        has_login_dom = await page.evaluate("""() => {
            const els = document.querySelectorAll('[class*="login"], [id*="login"]');
            for (const el of els) {
                const text = (el.innerText || '').trim();
                if (el.querySelector('canvas, img') && /扫码|二维码/.test(text)) return true;
            }
            return false;
        }""")
        if has_login_dom:
            return "页面存在登录二维码弹窗"
    except Exception:
        return ""
    return ""


def raise_login_wall(reason: str, where: str):
    """打印醒目中文错误并抛出 LoginWallError 中断运行。"""
    print("=" * 70)
    print(f"[ERROR] 检测到抖音登录墙（{where}）：{reason}")
    print("[ERROR] 登录态已失效，中断本次作者统计后处理（已拿到的数据仍会写盘）！")
    print("  - 标准 Playwright 模式：删除/重建登录态目录 browser_data/douyin_user_data_dir 后重新扫码登录；")
    print("  - CDP 模式：请在已连接的 Chrome 浏览器里手动登录抖音后重试。")
    print("=" * 70)
    raise LoginWallError(reason)


async def resolve_sec_uid_map(context, rows: list, sleep: float) -> tuple:
    """逐条访问视频页解析 aweme_id -> sec_uid 映射。

    返回 (映射, 熔断原因)；连续失败 MAX_CONSECUTIVE_RESOLVE_FAILURES 次即熔断，
    熔断原因非空表示运行被中断。LoginWallError 不在此捕获，直接向上抛出。
    """
    mapping = {}
    consecutive_failures = 0
    total = len(rows)
    for idx, r in enumerate(rows, 1):
        aweme_id = str(r.get("aweme_id", "")).strip()
        if not aweme_id or aweme_id in mapping:
            continue
        sec_uid = await resolve_sec_uid_from_video(
            context, aweme_id, str(r.get("aweme_url", "")).strip()
        )
        if sec_uid:
            mapping[aweme_id] = sec_uid
            consecutive_failures = 0
            print(f"  [{idx}/{total}] aweme_id={aweme_id} -> sec_uid={sec_uid[:12]}...")
        else:
            consecutive_failures += 1
            print(f"  [{idx}/{total}] aweme_id={aweme_id} 解析失败（连续 {consecutive_failures} 次）")
            if consecutive_failures >= MAX_CONSECUTIVE_RESOLVE_FAILURES:
                reason = (
                    f"视频页 sec_uid 解析连续失败 {MAX_CONSECUTIVE_RESOLVE_FAILURES} 次，"
                    "疑似页面结构变化或触发风控，已熔断中断"
                )
                print(f"[ERROR] {reason}")
                return mapping, reason
        await asyncio.sleep(sleep)
    return mapping, ""


async def extract_author_stats(context, sec_uid: str) -> dict:
    """访问单个作者主页并提取用户级数据。失败时返回 extraction_source=none 的空记录。"""
    extract_ts = int(datetime.now().timestamp())
    row = empty_author_row(sec_uid, extract_ts)
    page = None
    try:
        page = await context.new_page()
        url = AUTHOR_PAGE_URL.format(sec_uid=sec_uid)
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)  # 等待 SSR 注水与页面渲染

        # 登录墙检测：命中则中断整个运行（不再继续空转后续页面）
        wall_reason = await detect_login_wall(page)
        if wall_reason:
            raise_login_wall(wall_reason, f"作者主页 sec_uid={sec_uid}")

        # ① SSR 主路径（旧版页面）；失败后走 fiber 定向提取（新版页面数据在 React fiber 树里）
        ssr_user = None
        extraction_source = "ssr"
        try:
            ssr_info = await page.evaluate(SSR_PROBE_JS)
            if ssr_info:
                ssr_user = extract_user_from_ssr(ssr_info.get("data"), sec_uid)
        except Exception as exc:
            print(f"  [warn] SSR 探查失败 sec_uid={sec_uid}: {exc}")

        if not ssr_user:
            try:
                fiber_node = await evaluate_until(page, AUTHOR_FIBER_JS, arg=sec_uid)
                if fiber_node:
                    ssr_user = normalize_fiber_user(fiber_node)
                    extraction_source = "fiber"
            except Exception as exc:
                print(f"  [warn] fiber 提取失败 sec_uid={sec_uid}: {exc}")

        innertext_stats = {}
        if ssr_user:
            row["uid"] = str(ssr_user.get("uid", "") or "")
            row["nickname"] = str(ssr_user.get("nickname", "") or "")
            row["signature"] = str(ssr_user.get("signature", "") or "")
            row["ip_location"] = str(ssr_user.get("ip_location", "") or "")
            for field in ("follower_count", "total_favorited", "following_count", "aweme_count"):
                value = parse_count_abbr(ssr_user.get(field))
                if value >= 0:
                    row[field] = value
            parse_cert_from_ssr(ssr_user, row)
            row["extraction_source"] = extraction_source

        # ② innerText 兜底：SSR 缺失的数值字段用 innerText 补齐；SSR 失败则整行兜底
        need_innertext = (not ssr_user) or any(
            row[f] == "" for f in ("follower_count", "total_favorited", "following_count")
        ) or not row["is_verified"]
        if need_innertext:
            try:
                body_text = await page.evaluate(BODY_TEXT_JS)
                innertext_stats = parse_innertext(body_text or "")
            except Exception as exc:
                print(f"  [warn] innerText 解析失败 sec_uid={sec_uid}: {exc}")
            for field in ("total_favorited", "follower_count", "following_count"):
                if row[field] == "" and field in innertext_stats:
                    row[field] = innertext_stats[field]
            if not row["is_verified"] and innertext_stats.get("is_verified"):
                row["is_verified"] = 1
                row["custom_verify"] = innertext_stats.get("custom_verify", "")
                row["verification_type"] = innertext_stats.get("verification_type", "")
            if not ssr_user and innertext_stats:
                row["extraction_source"] = "innertext"
    except LoginWallError:
        raise  # 登录墙异常必须向上传播，不能被单作者失败兜底吞掉
    except Exception as exc:
        print(f"  [warn] 作者主页访问失败 sec_uid={sec_uid}: {exc}")
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass
    return row


async def resolve_sec_uid_from_video(context, aweme_id: str, aweme_url: str) -> str:
    """访问视频页解析作者 sec_uid（search_contents 不含 sec_uid 时的回退路径）。

    主路径走 DOM 提取主作者链接（新版页面无 SSR 全局变量）；
    保留旧版 SSR 探查与 HTML 正则作为兜底。
    """
    url = aweme_url or VIDEO_PAGE_URL.format(aweme_id=aweme_id)
    page = None
    try:
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(2)

        # 登录墙检测：命中则中断整个运行（不再继续空转后续页面）
        wall_reason = await detect_login_wall(page)
        if wall_reason:
            raise_login_wall(wall_reason, f"视频页 aweme_id={aweme_id}")

        try:
            sec_uid = await evaluate_until(page, VIDEO_AUTHOR_JS)
            if sec_uid:
                return sec_uid
        except Exception as exc:
            print(f"  [warn] 视频页 DOM 解析失败 aweme_id={aweme_id}: {exc}")

        try:
            ssr_info = await page.evaluate(SSR_PROBE_JS)
            if ssr_info:
                sec_uid = find_first_sec_uid(ssr_info.get("data"))
                if sec_uid:
                    return sec_uid
        except Exception as exc:
            print(f"  [warn] 视频页 SSR 探查失败 aweme_id={aweme_id}: {exc}")
        # 兜底：直接扫 HTML
        html = await page.content()
        m = re.search(r'"sec_uid"\s*:\s*"([A-Za-z0-9_\-]+)"', html)
        if m:
            return m.group(1)
    except LoginWallError:
        raise  # 登录墙异常必须向上传播，不能被单条失败兜底吞掉
    except Exception as exc:
        print(f"  [warn] 视频页访问失败 aweme_id={aweme_id}: {exc}")
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass
    return ""


async def create_browser_context(playwright, args):
    """创建浏览器上下文：优先 CDP 连接已有 Chrome，失败自动降级标准 Playwright。

    返回 (context, browser_or_none)。标准模式使用持久化用户数据目录以复用登录态，
    目录约定与 crawler 一致：{MediaCrawler}/browser_data/douyin_user_data_dir。
    """
    if args.cdp:
        # 新版 Chrome 可能只把调试端口绑在 IPv6 [::1] 上，127.0.0.1 会被拒，优先 localhost
        for host in ("localhost", "127.0.0.1"):
            endpoint = f"http://{host}:{args.cdp_port}"
            try:
                print(f"尝试 CDP 连接已有浏览器: {endpoint}")
                browser = await playwright.chromium.connect_over_cdp(endpoint, timeout=15000)
                if browser.contexts:
                    print("CDP 连接成功，复用现有浏览器上下文")
                    return browser.contexts[0], browser
                context = await browser.new_context(viewport={"width": 1920, "height": 1080})
                print("CDP 连接成功，已新建浏览器上下文")
                return context, browser
            except Exception as exc:
                print(f"CDP 连接失败（{exc}）")
        print("CDP 两种地址均连接失败，降级到标准 Playwright 模式")

    # 标准 Playwright 模式：持久化上下文复用 crawler 的登录态缓存目录
    user_data_dir = args.user_data_dir or os.path.join(
        DEFAULT_MEDIACRAWLER_ROOT, "browser_data", "douyin_user_data_dir"
    )
    os.makedirs(user_data_dir, exist_ok=True)
    print(f"启动标准 Playwright 浏览器，用户数据目录: {user_data_dir}")
    context = await playwright.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        headless=args.headless,
        viewport={"width": 1920, "height": 1080},
        accept_downloads=True,
    )
    # 与 crawler 一致注入反检测脚本（存在才注入）
    stealth_path = os.path.join(DEFAULT_MEDIACRAWLER_ROOT, "libs", "stealth.min.js")
    if os.path.exists(stealth_path):
        try:
            await context.add_init_script(path=stealth_path)
        except Exception as exc:
            print(f"[warn] 注入 stealth 脚本失败: {exc}")
    return context, None


async def run(args) -> bool:
    """主流程。返回 True 表示完整跑完；False 表示被登录墙/熔断中断（部分结果已写盘）。"""
    # 1. 读取 search_contents
    search_path = args.search
    if not search_path:
        # 默认取最新文件：csv 优先（与 SAVE_DATA_OPTION=csv 的默认目录约定一致），没有再找 jsonl
        try:
            search_path = find_latest_file(
                os.path.join(args.data_root, "douyin", "csv", "search_contents_*.csv")
            )
        except FileNotFoundError:
            search_path = find_latest_file(
                os.path.join(args.data_root, "douyin", "jsonl", "search_contents_*.jsonl")
            )
    print(f"search_contents: {search_path}")
    rows = read_rows(search_path)
    print(f"共读取 {len(rows)} 条视频记录")

    # 决定输出字段：提取逻辑不变（页面都开了，全部提取无额外成本），仅输出列按选择过滤
    selected_fields, fields_source = resolve_selected_fields(args)
    output_fieldnames = build_output_fieldnames(selected_fields)
    print(f"作者字段来源：{fields_source}")
    print(f"生效可选字段（{len(selected_fields)} 个）：{','.join(selected_fields) if selected_fields else '（无，仅固定列）'}")
    print(f"输出列：{','.join(output_fieldnames)}")

    from playwright.async_api import async_playwright

    aborted = False  # 被登录墙或熔断器中断时置 True
    aweme_author_map = {}  # aweme_id -> sec_uid
    author_rows = []
    success = 0
    async with async_playwright() as pw:
        context, browser = await create_browser_context(pw, args)
        try:
            # 2. 建立 aweme_id -> sec_uid 映射
            sec_uid_col = next((c for c in SEC_UID_COLUMNS if any(r.get(c) for r in rows)), None)
            if sec_uid_col:
                print(f"search_contents 含 {sec_uid_col} 列，直接取用，无需解析视频页")
                for r in rows:
                    aweme_id = str(r.get("aweme_id", "")).strip()
                    sec_uid = str(r.get(sec_uid_col, "")).strip()
                    if aweme_id and sec_uid:
                        aweme_author_map[aweme_id] = sec_uid
            else:
                print("search_contents 不含 sec_uid 列，将逐条访问视频页解析作者 sec_uid")
                aweme_author_map, abort_reason = await resolve_sec_uid_map(context, rows, args.sleep)
                if abort_reason:
                    aborted = True

            if not aborted:
                # 3. 作者去重
                unique_sec_uids = list(dict.fromkeys(aweme_author_map.values()))
                print(f"去重后共 {len(unique_sec_uids)} 位作者待访问")
                if args.max_authors > 0:
                    unique_sec_uids = unique_sec_uids[: args.max_authors]
                    print(f"--max-authors 生效，仅处理前 {len(unique_sec_uids)} 位")

                # 4. 逐个访问作者主页提取用户级数据，单个失败不中断整体
                for idx, sec_uid in enumerate(unique_sec_uids, 1):
                    nickname_hint = ""
                    for r in rows:
                        if aweme_author_map.get(str(r.get("aweme_id", "")).strip()) == sec_uid:
                            nickname_hint = str(r.get("nickname", ""))
                            break
                    print(f"[{idx}/{len(unique_sec_uids)}] 访问作者主页 sec_uid={sec_uid[:12]}... ({nickname_hint})")
                    row = await extract_author_stats(context, sec_uid)
                    author_rows.append(row)
                    if row["extraction_source"] != "none":
                        success += 1
                    if idx < len(unique_sec_uids):
                        await asyncio.sleep(args.sleep)
        except LoginWallError:
            aborted = True
        finally:
            # 清理：标准模式关闭上下文；CDP 模式只断开连接，不动用户的浏览器
            try:
                if browser:
                    await browser.close()
                else:
                    await context.close()
            except Exception:
                pass

    # 5. 输出作者级文件与 aweme_id -> sec_uid 映射文件（被中断时已拿到的部分结果也写盘）
    out_dir = Path(args.data_root) / "douyin" / "author_stats"
    out_dir.mkdir(parents=True, exist_ok=True)
    run_ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    output_path = args.output or str(out_dir / f"author_stats_{run_ts}.{args.format}")
    write_rows(output_path, author_rows, output_fieldnames, args.format)

    map_rows = [{"aweme_id": k, "sec_uid": v} for k, v in aweme_author_map.items()]
    map_path = args.map_output or str(out_dir / f"author_map_{run_ts}.{args.format}")
    write_rows(map_path, map_rows, ["aweme_id", "sec_uid"], args.format)

    # 6. 打印成功/失败统计
    failed = len(author_rows) - success
    print(f"作者统计输出：{output_path}")
    print(f"作者映射输出：{map_path}")
    print(f"共 {len(author_rows)} 位作者，成功 {success}，失败 {failed}")
    if aborted:
        print("[WARN] 本次运行被中断（登录墙或连续失败熔断），以上为部分结果，退出码置为非 0")
    return not aborted


def main():
    parser = argparse.ArgumentParser(
        description="作者统计数据后处理：对 search_contents 作者去重后访问主页，提取 UID/签名/IP 属地/粉丝数/总获赞数/认证信息。"
    )
    parser.add_argument(
        "--search",
        help="search_contents 文件路径（csv 或 jsonl）；省略则自动查找最新文件。",
    )
    parser.add_argument(
        "--data-root",
        default=DEFAULT_OUTPUT_ROOT,
        help=f"数据根目录（SAVE_DATA_PATH）；默认 {DEFAULT_OUTPUT_ROOT}。",
    )
    parser.add_argument(
        "--format",
        choices=["csv", "jsonl"],
        default="csv",
        help="输出格式；默认 csv。",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="作者统计输出文件路径；默认 {数据目录}/douyin/author_stats/author_stats_YYYY-MM-DD_HHMMSS.{csv|jsonl}。",
    )
    parser.add_argument(
        "--map-output",
        help="aweme_id -> sec_uid 映射输出路径；默认与作者统计文件同目录。",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=3.0,
        help="每次访问之间的间隔秒数（对应 CRAWLER_MAX_SLEEP_SEC 含义）；默认 3 秒。",
    )
    parser.add_argument(
        "--cdp",
        dest="cdp",
        action="store_true",
        default=True,
        help="优先通过 CDP 连接已打开的 Chrome（默认开启）。",
    )
    parser.add_argument(
        "--no-cdp",
        dest="cdp",
        action="store_false",
        help="不使用 CDP，直接用标准 Playwright 启动浏览器。",
    )
    parser.add_argument(
        "--cdp-port",
        type=int,
        default=9222,
        help="CDP 调试端口；默认 9222（对应 CDP_DEBUG_PORT）。",
    )
    parser.add_argument(
        "--user-data-dir",
        help="标准 Playwright 模式的用户数据目录；默认复用 crawler 的 browser_data/douyin_user_data_dir。",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="标准 Playwright 模式下使用无头浏览器；默认有头（与 crawler HEADLESS=False 一致）。",
    )
    parser.add_argument(
        "--fields",
        help="逗号分隔的作者字段清单（如 uid,follower_count），优先级最高；"
             "可选值见 AUTHOR_STAT_FIELD_DESCRIPTIONS，sec_uid/extraction_source/extract_ts/extract_ts_date 为固定必出列。",
    )
    parser.add_argument(
        "--all",
        dest="all_fields",
        action="store_true",
        help="忽略 author_stats_fields.json 配置文件，输出全部可选字段。",
    )
    parser.add_argument(
        "--max-authors",
        type=int,
        default=0,
        help="最多处理的作者数（调试用）；0 表示全部。",
    )
    args = parser.parse_args()

    completed = asyncio.run(run(args))
    if not completed:
        # 被中断（登录墙/熔断）时以非 0 退出码标识未完成，方便上层（如 server.py 自动触发）感知
        sys.exit(1)


if __name__ == "__main__":
    main()
