"""端到端流水线：scan → extract → lookup → plan → apply。

各阶段串行，避免 SQLite 写冲突。每阶段输出进度并落 logs/pipeline.log。
中断后再跑会自动从断点继续。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from . import (
    db, scan as scan_mod, extract as extract_mod, lookup as lookup_mod,
    organize as organize_mod, dedupe as dedupe_mod,
)

from .paths import BOOKS_ROOT as DEFAULT_ROOT, ORGANIZED_DIR as DEFAULT_ORGANIZED, LOG_FILE


def log(msg: str):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, file=sys.stderr, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_pipeline(
    db_path: Path,
    root: Path,
    organized: Path,
    *,
    exclude_dirs: set[str],
    extract_exts: list[str],
    lookup_limit: int | None,
    skip_scan: bool = False,
    skip_extract: bool = False,
    skip_lookup: bool = False,
    skip_apply: bool = False,
) -> int:
    log(f"=== pipeline start === root={root} db={db_path}")
    log(f"exclude_dirs={exclude_dirs} extract_exts={extract_exts}")

    # 阶段 1：扫盘
    if not skip_scan:
        log("phase 1/5 scan: starting")
        conn = db.connect(db_path)
        db.init(conn)
        t0 = time.time()
        stats = scan_mod.scan(conn, root, extra_skip=exclude_dirs)
        conn.close()
        log(f"phase 1/5 scan: done in {time.time()-t0:.0f}s — {stats}")
    else:
        log("phase 1/5 scan: SKIPPED")

    # 阶段 2：本地元数据
    if not skip_extract:
        log(f"phase 2/5 extract: starting (exts={extract_exts})")
        conn = db.connect(db_path)
        db.init(conn)
        t0 = time.time()
        stats = extract_mod.extract_all(conn, root, exts=extract_exts, limit=None,
                                         force=False, workers=6)
        conn.close()
        log(f"phase 2/5 extract: done in {time.time()-t0:.0f}s — {stats}")
    else:
        log("phase 2/5 extract: SKIPPED")

    # 阶段 3：在线补全
    if not skip_lookup:
        log(f"phase 3/5 lookup: starting (limit={lookup_limit})")
        conn = db.connect(db_path)
        db.init(conn)
        t0 = time.time()
        stats = lookup_mod.lookup_all(conn, limit=lookup_limit, force=False)
        conn.close()
        log(f"phase 3/5 lookup: done in {time.time()-t0:.0f}s — {stats}")
    else:
        log("phase 3/5 lookup: SKIPPED")

    # 阶段 4：dedupe（版本/重复聚类）
    log("phase 4/6 dedupe: starting")
    conn = db.connect(db_path)
    db.init(conn)
    t0 = time.time()
    stats = dedupe_mod.cluster_all(conn)
    conn.close()
    log(f"phase 4/6 dedupe: done in {time.time()-t0:.0f}s — {stats}")

    # 阶段 5：plan（只规划 primary）
    log("phase 5/6 plan: starting")
    conn = db.connect(db_path)
    db.init(conn)
    t0 = time.time()
    stats = organize_mod.plan_all(conn, min_confidence=0.6, limit=None)
    conn.close()
    log(f"phase 5/6 plan: done in {time.time()-t0:.0f}s — {stats}")

    # 阶段 6：apply（建立硬链接 / symlink）
    if not skip_apply:
        log(f"phase 6/6 apply: starting → {organized}")
        conn = db.connect(db_path)
        db.init(conn)
        t0 = time.time()
        stats = organize_mod.apply_all(conn, root, organized_dir=organized)
        conn.close()
        log(f"phase 6/6 apply: done in {time.time()-t0:.0f}s — {stats}")
    else:
        log("phase 6/6 apply: SKIPPED")

    log("=== pipeline complete ===")
    return 0
