"""为 metadata 表补充检索/排序用的冗余字段。

- title_sort: 把书名首字母转拼音(中文→拼音首字母 + 完整拼音),用于"按拼音 A-Z"排序
- pub_year:   从 pubdate(ISO 字符串或纯年份)抽出年份整数,用于按年代分组

回填是惰性的:web 启动时只保证列存在,不计算;用 `python -m books_organizer reindex`
一次性把所有空值算好。后续每次进新数据时也由 reindex 增量补齐。
"""
from __future__ import annotations

import re
import sqlite3
import sys
import time
from typing import Iterable


def ensure_columns(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(metadata)")}
    if "title_sort" not in cols:
        conn.execute("ALTER TABLE metadata ADD COLUMN title_sort TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_meta_title_sort ON metadata(title_sort)")
    if "pub_year" not in cols:
        conn.execute("ALTER TABLE metadata ADD COLUMN pub_year INTEGER")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_meta_pub_year ON metadata(pub_year)")
    conn.commit()


_YEAR_RE = re.compile(r"(\d{4})")


def parse_year(pubdate: str | None) -> int | None:
    if not pubdate:
        return None
    m = _YEAR_RE.search(pubdate)
    if not m:
        return None
    y = int(m.group(1))
    return y if 1500 <= y <= 2100 else None


def _pinyin_key(title: str) -> str:
    """返回大写拼音字符串;非中文字符按原样大写带入。"""
    from pypinyin import lazy_pinyin, Style

    parts = lazy_pinyin(title, style=Style.NORMAL, errors="default")
    return "".join(parts).upper()


_TITLE_PREFIX_TRIM = "《〈[(\"'【「『（〔〖〘〚 \t\n\r"
_VALID_FIRST = re.compile(r"[一-鿿㐀-䶿A-Za-z0-9]")


def title_sort_key(title: str | None) -> str:
    if not title:
        return "ZZZ"  # 排到最后
    s = title.strip().lstrip(_TITLE_PREFIX_TRIM)
    if not s:
        return "ZZZ"
    m = _VALID_FIRST.search(s)
    if not m:
        return "ZZZ"
    s = s[m.start():]
    try:
        key = _pinyin_key(s)[:80]
        return key if key.strip() else "ZZZ"
    except Exception:
        return s.upper()[:80]


def reindex(conn: sqlite3.Connection, force: bool = False,
            batch: int = 500) -> dict:
    """回填 title_sort 与 pub_year。force=True 时全表重算,否则只补空值。"""
    ensure_columns(conn)
    where = "" if force else "WHERE title_sort IS NULL OR pub_year IS NULL"
    total = conn.execute(
        f"SELECT COUNT(*) FROM metadata m WHERE m.title IS NOT NULL AND m.title!='' "
        + ("" if force else "AND (m.title_sort IS NULL OR m.pub_year IS NULL)")
    ).fetchone()[0]
    if total == 0:
        return {"total": 0, "updated": 0, "elapsed": 0.0}

    print(f"reindex: {total} rows to process", file=sys.stderr)
    t0 = time.time()
    updated = 0
    rows = conn.execute(
        f"SELECT file_id, title, pubdate FROM metadata m "
        f"WHERE m.title IS NOT NULL AND m.title != '' "
        + ("" if force else "AND (m.title_sort IS NULL OR m.pub_year IS NULL)")
    ).fetchall()

    pending: list[tuple] = []
    for r in rows:
        ts = title_sort_key(r["title"])
        py = parse_year(r["pubdate"])
        pending.append((ts, py, r["file_id"]))
        if len(pending) >= batch:
            conn.executemany(
                "UPDATE metadata SET title_sort=?, pub_year=? WHERE file_id=?",
                pending,
            )
            conn.commit()
            updated += len(pending)
            pending.clear()
            print(f"  reindex: {updated}/{total}", file=sys.stderr)

    if pending:
        conn.executemany(
            "UPDATE metadata SET title_sort=?, pub_year=? WHERE file_id=?",
            pending,
        )
        conn.commit()
        updated += len(pending)

    dt = time.time() - t0
    print(f"reindex done — updated={updated} in {dt:.1f}s", file=sys.stderr)
    return {"total": total, "updated": updated, "elapsed": dt}
