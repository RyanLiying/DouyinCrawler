#!/usr/bin/env python3
"""Merge Douyin search_contents and extra_fields CSV by aweme_id, with timestamp conversion.

可选步骤：若发现 author_stats 文件（enrich_author_stats.py 的输出），
按 sec_uid 左连接作者级字段（列名带 author_ 前缀）到合并结果。
"""

import argparse
import csv
import json
import os
from datetime import datetime, timedelta, timezone
from glob import glob
from pathlib import Path

DEFAULT_OUTPUT_ROOT = str(Path(__file__).resolve().parents[2] / "data-outputs")

TS_DATE_COLUMNS = [
    ("create_time", "create_time_date", "s"),
    ("last_modify_ts", "last_modify_ts_date", "ms"),
    ("extra_extract_ts", "extra_extract_ts_date", "ms"),
    ("author_extract_ts", "author_extract_ts_date", "s"),
]

# 合并到最终结果里的作者级字段（author_stats 文件中的列，输出时带 author_ 前缀）
AUTHOR_MERGE_FIELDS = [
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
    "extraction_source",
    "extract_ts",
]


def find_latest_file(pattern: str) -> str:
    files = glob(pattern)
    if not files:
        raise FileNotFoundError(f"找不到匹配文件: {pattern}")
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files[0]


def read_extra_fields(path: str) -> dict:
    extra = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            aweme_id = str(row.get("aweme_id", "")).strip()
            if aweme_id:
                extra[aweme_id] = row
    return extra


def read_author_stats(path: str) -> dict:
    """读取 author_stats 文件（csv 或 jsonl），按 sec_uid 建索引。"""
    authors = {}
    if path.endswith(".jsonl"):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                sec_uid = str(row.get("sec_uid", "")).strip()
                if sec_uid:
                    authors[sec_uid] = row
    else:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sec_uid = str(row.get("sec_uid", "")).strip()
                if sec_uid:
                    authors[sec_uid] = row
    return authors


def read_author_map(path: str) -> dict:
    """读取 aweme_id -> sec_uid 映射文件（csv 或 jsonl）。"""
    mapping = {}
    if path.endswith(".jsonl"):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                aweme_id = str(row.get("aweme_id", "")).strip()
                sec_uid = str(row.get("sec_uid", "")).strip()
                if aweme_id and sec_uid:
                    mapping[aweme_id] = sec_uid
    else:
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                aweme_id = str(row.get("aweme_id", "")).strip()
                sec_uid = str(row.get("sec_uid", "")).strip()
                if aweme_id and sec_uid:
                    mapping[aweme_id] = sec_uid
    return mapping


def ts_to_date(value: str, unit: str = "s") -> str:
    try:
        ts = int(value)
        if not ts:
            return ""
        if unit == "ms":
            ts = ts / 1000
        tz = timezone(timedelta(hours=8))
        return datetime.fromtimestamp(ts, tz).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def insert_date_columns(fieldnames: list) -> list:
    seen = set()
    new_fieldnames = []
    for col in fieldnames:
        new_fieldnames.append(col)
        seen.add(col)
        for src, dst, _ in TS_DATE_COLUMNS:
            if col == src and dst not in seen:
                new_fieldnames.append(dst)
                seen.add(dst)
    return new_fieldnames


def merge_files(search_path: str, extra_path: str, output_path: str,
                author_stats_path: str = "", author_map_path: str = ""):
    extra = read_extra_fields(extra_path)

    # 可选：加载作者统计数据，按 sec_uid 左连接
    authors = {}
    aweme_sec_uid_map = {}
    if author_stats_path:
        authors = read_author_stats(author_stats_path)
        print(f"author_stats:    {author_stats_path}（{len(authors)} 位作者）")
        if author_map_path:
            aweme_sec_uid_map = read_author_map(author_map_path)
            print(f"author_map:      {author_map_path}（{len(aweme_sec_uid_map)} 条映射）")
    else:
        print("未发现 author_stats 文件，跳过作者统计合并（可先运行 enrich_author_stats.py 生成）。")

    # 与 author_stats 文件实际存在的列取交集：未勾选的字段不产生空列
    author_fields = []
    if authors:
        available = set()
        for r in authors.values():
            available.update(r.keys())
        author_fields = [f for f in AUTHOR_MERGE_FIELDS if f in available]

    with open(search_path, "r", encoding="utf-8-sig", newline="") as sf:
        search_reader = csv.DictReader(sf)
        search_fieldnames = search_reader.fieldnames or []

        with open(extra_path, "r", encoding="utf-8-sig", newline="") as ef:
            extra_reader = csv.DictReader(ef)
            extra_fieldnames = extra_reader.fieldnames or []

        extra_fieldnames = [c for c in extra_fieldnames if c != "aweme_id"]
        merged_fieldnames = insert_date_columns(search_fieldnames + extra_fieldnames)

        # 作者列：追加 sec_uid（若原表没有）+ author_ 前缀字段
        author_join_enabled = bool(authors)
        if author_join_enabled:
            if "sec_uid" not in merged_fieldnames and "sec_uid" not in search_fieldnames:
                merged_fieldnames.append("sec_uid")
            for field in author_fields:
                col = f"author_{field}"
                if col not in merged_fieldnames:
                    merged_fieldnames.append(col)
            merged_fieldnames = insert_date_columns(merged_fieldnames)

        with open(output_path, "w", encoding="utf-8-sig", newline="") as out:
            writer = csv.DictWriter(out, fieldnames=merged_fieldnames)
            writer.writeheader()
            matched = 0
            unmatched = 0
            author_matched = 0
            for row in search_reader:
                aweme_id = str(row.get("aweme_id", "")).strip()
                extra_row = extra.get(aweme_id, {})
                merged_row = dict(row)
                for c in extra_fieldnames:
                    merged_row[c] = extra_row.get(c, "")
                if author_join_enabled:
                    # sec_uid 优先取原表列，缺失时走 aweme_id 映射
                    sec_uid = str(merged_row.get("sec_uid", "")).strip() or aweme_sec_uid_map.get(aweme_id, "")
                    merged_row["sec_uid"] = sec_uid
                    author_row = authors.get(sec_uid, {})
                    for field in author_fields:
                        merged_row[f"author_{field}"] = author_row.get(field, "")
                    if author_row:
                        author_matched += 1
                for src, dst, unit in TS_DATE_COLUMNS:
                    if src in merged_row:
                        merged_row[dst] = ts_to_date(merged_row[src], unit)
                writer.writerow(merged_row)
                if extra_row:
                    matched += 1
                else:
                    unmatched += 1

    print(f"合并完成：{output_path}")
    print(f"总记录数：{matched + unmatched}，成功匹配扩展字段：{matched}，未匹配：{unmatched}")
    if author_join_enabled:
        print(f"成功匹配作者统计：{author_matched}，未匹配：{matched + unmatched - author_matched}")


def main():
    parser = argparse.ArgumentParser(
        description="根据 aweme_id 合并 Douyin search_contents.csv 和 extra_fields.csv。"
    )
    parser.add_argument(
        "--search",
        help="search_contents CSV 文件路径；省略则自动查找最新文件。",
    )
    parser.add_argument(
        "--extra",
        help="extra_fields CSV 文件路径；省略则自动查找最新文件。",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="输出文件路径；默认写入 {DEFAULT_OUTPUT_ROOT}/douyin/merged/merged_YYYY-MM-DD_HHMMSS.csv。",
    )
    parser.add_argument(
        "--author-stats",
        help="author_stats 文件路径（csv 或 jsonl）；省略则自动查找最新文件，找不到则跳过作者合并。",
    )
    parser.add_argument(
        "--author-map",
        help="aweme_id -> sec_uid 映射文件路径（csv 或 jsonl）；省略则自动查找最新文件。",
    )
    parser.add_argument(
        "--no-author",
        action="store_true",
        help="强制跳过作者统计合并，行为与旧版完全一致。",
    )
    args = parser.parse_args()

    search_path = args.search
    extra_path = args.extra

    if not search_path:
        search_pattern = os.path.join(DEFAULT_OUTPUT_ROOT, "douyin", "csv", "search_contents_*.csv")
        search_path = find_latest_file(search_pattern)
    if not extra_path:
        extra_pattern = os.path.join(DEFAULT_OUTPUT_ROOT, "douyin", "extra_fields", "extra_fields_*.csv")
        extra_path = find_latest_file(extra_pattern)

    print(f"search_contents: {search_path}")
    print(f"extra_fields:    {extra_path}")

    # 可选：自动查找 author_stats 与 author_map（csv 优先，其次 jsonl）
    author_stats_path = ""
    author_map_path = ""
    if not args.no_author:
        author_stats_path = args.author_stats or ""
        if not author_stats_path:
            for pattern in (
                os.path.join(DEFAULT_OUTPUT_ROOT, "douyin", "author_stats", "author_stats_*.csv"),
                os.path.join(DEFAULT_OUTPUT_ROOT, "douyin", "author_stats", "author_stats_*.jsonl"),
            ):
                try:
                    author_stats_path = find_latest_file(pattern)
                    break
                except FileNotFoundError:
                    continue
        author_map_path = args.author_map or ""
        if author_stats_path and not author_map_path:
            for pattern in (
                os.path.join(DEFAULT_OUTPUT_ROOT, "douyin", "author_stats", "author_map_*.csv"),
                os.path.join(DEFAULT_OUTPUT_ROOT, "douyin", "author_stats", "author_map_*.jsonl"),
            ):
                try:
                    author_map_path = find_latest_file(pattern)
                    break
                except FileNotFoundError:
                    continue

    output_path = args.output
    if not output_path:
        merged_dir = Path(DEFAULT_OUTPUT_ROOT) / "douyin" / "merged"
        merged_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(merged_dir / f"merged_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.csv")

    merge_files(search_path, extra_path, output_path,
                author_stats_path=author_stats_path, author_map_path=author_map_path)


if __name__ == "__main__":
    main()
