#!/usr/bin/env python3
"""把一次抖音爬取的输出整理为一个 3-Sheet Excel：主表(视频+作者+评论聚合) / 评论表 / 作者表。"""

import argparse
import csv
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell

TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS_DIR))
from merge_douyin_outputs import DEFAULT_OUTPUT_ROOT, find_latest_file, merge_files

ILLEGAL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
MAX_CELL_LEN = 32767


def clean(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        return value
    return ILLEGAL_CHARS.sub("", value)[:MAX_CELL_LEN]


def read_csv_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            return [], []
        return header, [row for row in reader]


def resolve_paths(args):
    dy = os.path.join(DEFAULT_OUTPUT_ROOT, "douyin")
    search = args.search or find_latest_file(os.path.join(dy, "csv", "search_contents_*.csv"))
    extra = args.extra or find_latest_file(os.path.join(dy, "extra_fields", "extra_fields_*.csv"))
    comments = args.comments or find_latest_file(os.path.join(dy, "csv", "search_comments_*.csv"))
    author_stats = args.author_stats or find_latest_file(
        os.path.join(dy, "author_stats", "author_stats_*.csv")
    )
    author_map = args.author_map or find_latest_file(
        os.path.join(dy, "author_stats", "author_map_*.csv")
    )
    return search, extra, comments, author_stats, author_map


def text_cell(sheet, value):
    # openpyxl 会把以 "=" 开头的字符串当成公式，导致 Excel 打开时报「修复/已删除公式」；这里强制为文本
    value = clean(value)
    if not isinstance(value, str):
        return value
    cell = WriteOnlyCell(sheet, value=value)
    cell.data_type = "s"
    return cell


def write_sheet(workbook, name, header, rows):
    sheet = workbook.create_sheet(name)
    sheet.freeze_panes = "A2"
    sheet.append([text_cell(sheet, c) for c in header])
    for row in rows:
        sheet.append([text_cell(sheet, v) for v in row])


def build(args):
    search, extra, comments, author_stats, author_map = resolve_paths(args)
    print(f"search_contents: {search}")
    print(f"extra_fields:    {extra}")
    print(f"comments:        {comments}")
    print(f"author_stats:    {author_stats}")
    print(f"author_map:      {author_map}")

    fd, tmp = tempfile.mkstemp(prefix="douyin_merged_", suffix=".csv")
    os.close(fd)
    try:
        merge_files(
            search,
            extra,
            tmp,
            author_stats_path=author_stats,
            author_map_path=author_map,
            comments_path=comments,
        )
        main_header, main_rows = read_csv_rows(tmp)
    finally:
        os.remove(tmp)
    comment_header, comment_rows = read_csv_rows(comments)
    author_header, author_rows = read_csv_rows(author_stats)

    out = args.output or os.path.join(
        DEFAULT_OUTPUT_ROOT,
        "douyin",
        "merged",
        f"douyin_data_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.xlsx",
    )
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook(write_only=True)
    write_sheet(wb, "主表", main_header, main_rows)
    write_sheet(wb, "评论表", comment_header, comment_rows)
    write_sheet(wb, "作者表", author_header, author_rows)
    wb.save(out)

    print(f"\n生成: {out}")
    print(f"  主表:   {len(main_rows)} 行 x {len(main_header)} 列")
    print(f"  评论表: {len(comment_rows)} 行 x {len(comment_header)} 列")
    print(f"  作者表: {len(author_rows)} 行 x {len(author_header)} 列")


def main():
    parser = argparse.ArgumentParser(description="生成 3-Sheet 抖音数据 Excel。")
    parser.add_argument("--search")
    parser.add_argument("--extra")
    parser.add_argument("--comments")
    parser.add_argument("--author-stats")
    parser.add_argument("--author-map")
    parser.add_argument("--output", "-o")
    build(parser.parse_args())


if __name__ == "__main__":
    main()
