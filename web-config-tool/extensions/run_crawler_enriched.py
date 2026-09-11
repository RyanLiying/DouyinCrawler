#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MediaCrawler 抖音扩展字段运行包装器

本脚本用于替代直接运行 MediaCrawler/main.py，在保持原有 18 字段输出不变的同时，
通过运行时 monkey-patch 追加采集扩展字段（认证、音乐、话题、播放量等）。

用法：
    python web-config-tool/extensions/run_crawler_enriched.py

要求：
- 必须由 web-config-tool/server.py 在 MediaCrawler 根目录下启动
- 启动前 MediaCrawler/config/ 已替换为生成的临时配置（ENABLE_EXTRA_FIELDS 控制是否启用扩展字段）
"""

import asyncio
import os
import sys


def main():
    # 本脚本所在目录（extensions），用于导入 douyin_extra_fields
    extensions_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, extensions_dir)

    # server.py 在 MediaCrawler 根目录下启动本脚本，因此当前工作目录就是 MediaCrawler 根目录
    # 需要把它加入 sys.path，否则 import config / main 会失败
    project_dir = os.getcwd()
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)

    # 1. 加载 MediaCrawler 配置（server.py 已把生成配置写到 MediaCrawler/config/）
    import config

    selected_extra_fields = getattr(config, "SELECTED_EXTRA_FIELDS", [])
    if selected_extra_fields:
        print(f"[INFO] 已启用抖音扩展字段采集，选中字段: {selected_extra_fields}", flush=True)
        from douyin_extra_fields import patch_douyin_store

        patch_douyin_store()
    else:
        print("[INFO] 未启用扩展字段采集，仅保留标准 18 字段", flush=True)

    # 3. 运行 MediaCrawler 主入口
    from main import main as crawler_main

    asyncio.run(crawler_main())


if __name__ == "__main__":
    main()
