# -*- coding: utf-8 -*-
"""
MediaCrawler 抖音扩展字段提取模块

用途：在不修改 MediaCrawler 源码的前提下，通过 monkey-patch 在运行时追加采集
扩展字段。用户可通过 config.SELECTED_EXTRA_FIELDS 指定需要采集哪些字段。

提取结果单独写入 data/douyin/extra_fields/，文件格式跟随 config.SAVE_DATA_OPTION：
- 主格式为 csv 时，扩展字段也输出为 csv
- 其它格式统一输出为 jsonl
不影响原有 18 字段输出。研究者可通过 aweme_id 将两份数据 join 起来。
"""

import csv
import json
import os
from datetime import datetime
from typing import Any, Dict, List


def _get_nested(data: Dict[str, Any], *keys, default=""):
    """安全地获取嵌套字典字段。"""
    for key in keys:
        if not isinstance(data, dict):
            return default
        data = data.get(key, default)
    return data if data is not None else default


# 所有可选扩展字段的中文说明（用于前端展示和文档）
EXTRA_FIELD_DESCRIPTIONS = {
    "is_verified": "账号是否认证",
    "verification_type": "认证类型",
    "enterprise_verify_reason": "企业认证说明",
    "is_enterprise_vip": "是否企业号",
    "is_gov_media_vip": "是否政务号",
    "music_id": "音乐 ID",
    "music_title": "音乐名称",
    "music_author": "音乐作者",
    "play_count": "播放量",
    "challenge_tags": "话题/挑战标签",
    "is_ads": "是否广告",
    "has_anchor": "是否含商业锚点",
}


# 扩展字段默认值（用于前端初始化全选）
DEFAULT_SELECTED_EXTRA_FIELDS = list(EXTRA_FIELD_DESCRIPTIONS.keys())


def extract_extra_fields(aweme_item: Dict[str, Any]) -> Dict[str, Any]:
    """
    从抖音原始 aweme_info 中提取扩展字段，但只返回 SELECTED_EXTRA_FIELDS 中列出的字段。

    Args:
        aweme_item: 抖音接口返回的原始作品字典

    Returns:
        包含选中扩展字段的字典，aweme_id 始终保留用于关联
    """
    import config

    selected: List[str] = getattr(config, "SELECTED_EXTRA_FIELDS", DEFAULT_SELECTED_EXTRA_FIELDS) or []
    if not selected:
        return {"aweme_id": str(aweme_item.get("aweme_id", ""))}

    author = aweme_item.get("author", {}) or {}
    music = aweme_item.get("music", {}) or {}
    statistics = aweme_item.get("statistics", {}) or {}

    # 1. 话题标签：优先从 text_extra 取，没有再从 challenges 取
    tags = []
    text_extra = aweme_item.get("text_extra", []) or []
    for item in text_extra:
        if isinstance(item, dict):
            tag = item.get("hashtag_name")
            if tag:
                tags.append(str(tag))

    if not tags:
        challenges = aweme_item.get("challenges", []) or []
        for ch in challenges:
            if isinstance(ch, dict):
                tag = ch.get("cha_name")
                if tag:
                    tags.append(str(tag))

    # 2. 商业锚点
    anchors = aweme_item.get("anchors", []) or []
    has_anchor = len(anchors) > 0

    verification_type = author.get("verification_type", "")
    custom_verify = author.get("custom_verify", "")
    enterprise_verify_reason = author.get("enterprise_verify_reason", "")
    is_verified = int(author.get("is_verified", 0) or 0)
    if not is_verified and (str(verification_type) not in ("", "0") or custom_verify or enterprise_verify_reason):
        is_verified = 1
        import logging
        logging.info(f"[douyin_extra_fields] derived is_verified=1 for aweme_id={aweme_item.get('aweme_id')} verification_type={verification_type} custom_verify={custom_verify} enterprise_verify_reason={enterprise_verify_reason}")

    # 3. 完整候选字段池
    candidates = {
        "aweme_id": str(aweme_item.get("aweme_id", "")),
        "is_verified": is_verified,
        "verification_type": verification_type,
        "enterprise_verify_reason": enterprise_verify_reason,
        "is_enterprise_vip": int(author.get("is_enterprise_vip", 0) or 0),
        "is_gov_media_vip": int(author.get("is_gov_media_vip", 0) or 0),
        "music_id": str(_get_nested(music, "id", default="")),
        "music_title": _get_nested(music, "title", default=""),
        "music_author": _get_nested(music, "author", default=""),
        "play_count": str(_get_nested(statistics, "play_count", default="")),
        "challenge_tags": ",".join(tags),
        "is_ads": int(aweme_item.get("is_ads", 0) or 0),
        "has_anchor": int(has_anchor),
        "extra_extract_ts": int(datetime.now().timestamp() * 1000),
    }

    # 4. 只返回用户选中的字段 + aweme_id（用于关联）
    result = {"aweme_id": candidates["aweme_id"]}
    for key in selected:
        if key in candidates:
            result[key] = candidates[key]
    return result


class ExtraFieldStore:
    """
    扩展字段持久化：写入 data/douyin/extra_fields/，格式与主输出保持一致。
    不修改 MediaCrawler 原有存储路径和格式。
    """

    def __init__(self):
        self._format = self._resolve_format()
        self._file_path = self._resolve_file_path()
        self._ensure_dir()

    def _resolve_format(self) -> str:
        """根据 config.SAVE_DATA_OPTION 决定扩展字段输出格式。"""
        try:
            import config
            fmt = getattr(config, "SAVE_DATA_OPTION", "jsonl")
        except Exception:
            fmt = "jsonl"
        return fmt if fmt in ("csv",) else "jsonl"

    def _resolve_file_path(self) -> str:
        """解析输出文件路径：优先使用 config.SAVE_DATA_PATH，否则使用 MediaCrawler/data/douyin/extra_fields。"""
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        run_ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        try:
            import config
            save_data_path = getattr(config, "SAVE_DATA_PATH", "")
        except Exception:
            save_data_path = ""
        if save_data_path:
            data_dir = os.path.join(save_data_path, "douyin", "extra_fields")
        else:
            data_dir = os.path.join(project_root, "MediaCrawler", "data", "douyin", "extra_fields")
        return os.path.join(data_dir, f"extra_fields_{run_ts}.{self._format}")

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self._file_path), exist_ok=True)

    @staticmethod
    def _normalize(extra: Dict[str, Any]) -> Dict[str, Any]:
        """把空值统一处理为空字符串，避免 csv 出现 None。"""
        return {k: (v if v is not None else "") for k, v in extra.items()}

    def store(self, extra: Dict[str, Any]):
        """追加写入一条记录。"""
        extra = self._normalize(extra)
        if self._format == "csv":
            self._store_csv(extra)
        else:
            self._store_jsonl(extra)

    def _store_jsonl(self, extra: Dict[str, Any]):
        with open(self._file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(extra, ensure_ascii=False) + "\n")

    def _store_csv(self, extra: Dict[str, Any]):
        """CSV 以 aweme_id 开头，字段按字母序固定，缺失字段填空。"""
        import config
        selected: List[str] = getattr(config, "SELECTED_EXTRA_FIELDS", []) or []
        fieldnames = ["aweme_id"] + [k for k in EXTRA_FIELD_DESCRIPTIONS.keys() if k in selected]

        file_exists = os.path.exists(self._file_path) and os.path.getsize(self._file_path) > 0
        with open(self._file_path, "a", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            row = {name: extra.get(name, "") for name in fieldnames}
            writer.writerow(row)


# 单例
_extra_store: ExtraFieldStore | None = None


def _get_extra_store() -> ExtraFieldStore:
    global _extra_store
    if _extra_store is None:
        _extra_store = ExtraFieldStore()
    return _extra_store


def patch_douyin_store():
    """
    运行时 monkey-patch：在 MediaCrawler 原有 update_douyin_aweme 保存完标准字段后，
    追加保存扩展字段到单独的 JSONL 文件。

    注意：必须在 MediaCrawler 的 store.douyin 模块已加载后调用。
    """
    import config
    import store.douyin as douyin_store

    selected: List[str] = getattr(config, "SELECTED_EXTRA_FIELDS", [])
    if not selected:
        return

    original_update = douyin_store.update_douyin_aweme

    async def _wrapped_update(aweme_item: Dict[str, Any]):
        # 先走原逻辑，保证原有 18 字段不受影响
        await original_update(aweme_item)

        # 再提取并保存扩展字段
        try:
            extra = extract_extra_fields(aweme_item)
            _get_extra_store().store(extra)
        except Exception as exc:
            import logging
            logging.warning("[douyin_extra_fields] 扩展字段提取失败: %s", exc)

    douyin_store.update_douyin_aweme = _wrapped_update
