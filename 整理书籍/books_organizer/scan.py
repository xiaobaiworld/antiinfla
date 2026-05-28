"""阶段 1：扫盘建库。

只读。遍历 root，记录每个文件的相对路径、大小、mtime、快指纹（size + head 64k md5）。
断点续跑：若 (rel_path, size, mtime) 都未变，跳过指纹计算。
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import sys
import time
from pathlib import Path

BOOK_EXTS = {
    "pdf", "epub", "mobi", "azw", "azw3", "azw4",
    "txt", "doc", "docx", "chm", "djvu", "fb2",
    "prc", "lit", "rtf", "html", "htm",
}
ARCHIVE_EXTS = {"zip", "7z", "rar", "tar", "gz", "bz2", "xz", "tgz"}

# 跳过的目录名（NAS/系统/我们自己的输出）
SKIP_DIRS = {
    "@eaDir", "@SynoEAStream", "@SynoResource",
    ".Trashes", ".Spotlight-V100", ".fseventsd", ".TemporaryItems",
    "_组织后", "_organized",
}

HEAD_BYTES = 64 * 1024
PROGRESS_EVERY = 200
COMMIT_EVERY = 500


def classify(ext: str) -> str:
    if ext in BOOK_EXTS:
        return "book"
    if ext in ARCHIVE_EXTS:
        return "archive"
    return "other"


def fast_fingerprint(path: Path, size: int) -> str:
    """size + 文件头 64KB 的 md5。SMB 下避免全文件 hash。"""
    h = hashlib.md5(usedforsecurity=False)
    h.update(str(size).encode())
    try:
        with path.open("rb") as f:
            h.update(f.read(HEAD_BYTES))
    except (OSError, PermissionError):
        return ""
    return h.hexdigest()


def iter_files(root: Path, extra_skip: set[str] | None = None):
    """yield (abs_path, rel_path_str) 跳过隐藏/系统目录。"""
    skip = SKIP_DIRS | (extra_skip or set())
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.startswith(".")]
        for name in filenames:
            if name.startswith(".") or name == "Thumbs.db":
                continue
            abs_path = Path(dirpath) / name
            rel = abs_path.relative_to(root)
            yield abs_path, str(rel)


def scan(
    conn: sqlite3.Connection,
    root: Path,
    *,
    verbose: bool = True,
    compute_fingerprint: bool = False,
    extra_skip: set[str] | None = None,
) -> dict:
    """扫盘入库。返回统计字典。

    默认不算指纹（SMB 上每个文件 64KB 头读太慢）。指纹在去重阶段按需算。
    """
    stats = {"seen": 0, "new": 0, "unchanged": 0, "updated": 0, "errors": 0}
    now = time.time()
    cur = conn.cursor()

    existing: dict[str, tuple[int, float]] = {}
    for row in cur.execute("SELECT rel_path, size, mtime FROM files"):
        existing[row["rel_path"]] = (row["size"], row["mtime"])

    pending = 0
    t0 = time.time()
    for abs_path, rel in iter_files(root, extra_skip=extra_skip):
        stats["seen"] += 1
        try:
            st = abs_path.stat()
        except OSError:
            stats["errors"] += 1
            continue

        size = st.st_size
        mtime = st.st_mtime
        prev = existing.get(rel)

        if prev and prev[0] == size and abs(prev[1] - mtime) < 1.0:
            stats["unchanged"] += 1
        else:
            name = abs_path.name
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            kind = classify(ext)
            fp = fast_fingerprint(abs_path, size) if compute_fingerprint else ""

            cur.execute(
                """
                INSERT INTO files (rel_path, name, ext, size, mtime, fingerprint, kind, scanned_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rel_path) DO UPDATE SET
                    name=excluded.name,
                    ext=excluded.ext,
                    size=excluded.size,
                    mtime=excluded.mtime,
                    fingerprint=excluded.fingerprint,
                    kind=excluded.kind,
                    scanned_at=excluded.scanned_at
                """,
                (rel, name, ext, size, mtime, fp, kind, now),
            )
            if prev is None:
                stats["new"] += 1
            else:
                stats["updated"] += 1
            pending += 1
            if pending >= COMMIT_EVERY:
                conn.commit()
                pending = 0

        if verbose and stats["seen"] % PROGRESS_EVERY == 0:
            dt = time.time() - t0
            rate = stats["seen"] / dt if dt > 0 else 0
            print(
                f"  [{stats['seen']:>7}] new={stats['new']} updated={stats['updated']} "
                f"unchanged={stats['unchanged']} errors={stats['errors']} ({rate:.0f}/s)",
                file=sys.stderr, flush=True,
            )

    conn.commit()
    return stats
