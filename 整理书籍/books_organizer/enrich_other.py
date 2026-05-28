"""对 category='other' 的书抽前 N 字文本 + 重跑分类规则。

设计：
  - 从 BOOKS_ROOT 读 EPUB/PDF/TXT 抽文本（不依赖 calibre）
  - 抽出的文本 + 原 title + author + publisher + rel_path 一起喂 classify
  - 命中具体规则就 UPDATE，留 other 的不动
  - 失败的（损坏文件 / I/O 错误 / 编码问题）跳过，记 error 计数

用法：
  python -m books_organizer.enrich_other            # 跑全量
  python -m books_organizer.enrich_other --limit 100
  python -m books_organizer.enrich_other --ext epub  # 只跑 epub
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

from .classify import classify
from .paths import BOOKS_ROOT, DB_PATH


MAX_CHARS = 4000   # 单本抽多少字符喂规则
LOG_EVERY = 50     # 每 N 本输出一次进度


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[a-zA-Z]+;|&#\d+;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_epub_text(path: Path, max_chars: int = MAX_CHARS) -> str:
    from ebooklib import epub, ITEM_DOCUMENT
    book = epub.read_epub(str(path), options={"ignore_ncx": True})
    chunks: list[str] = []
    total = 0
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        try:
            body = item.get_body_content() or b""
            text = _strip_html(body.decode("utf-8", errors="ignore"))
            if text:
                chunks.append(text)
                total += len(text)
                if total >= max_chars:
                    break
        except Exception:
            continue
    return " ".join(chunks)[:max_chars]


def extract_pdf_text(path: Path, max_chars: int = MAX_CHARS) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    out = ""
    for i, page in enumerate(reader.pages[:5]):  # 前 5 页
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        out += t + " "
        if len(out) >= max_chars:
            break
    return out[:max_chars]


def extract_txt(path: Path, max_chars: int = MAX_CHARS) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ext", default="pdf,epub,txt", help="只跑这些扩展名")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    exts = tuple(e.strip() for e in args.ext.split(",") if e.strip())
    placeholders = ",".join("?" * len(exts))

    conn = sqlite3.connect(DB_PATH, timeout=60)
    sql = f"""
        SELECT m.file_id, m.title, m.author, m.publisher, f.rel_path, f.ext, f.size
        FROM metadata m JOIN files f ON m.file_id=f.id
        WHERE m.category = 'other' AND f.ext IN ({placeholders})
        ORDER BY f.size DESC
    """
    if args.limit:
        sql += f" LIMIT {args.limit}"
    rows = conn.execute(sql, exts).fetchall()
    print(f"待处理: {len(rows)} 本 (ext={exts})")
    if not rows:
        return 0

    t_start = time.time()
    n_extract_ok = 0
    n_changed = 0
    n_error = 0
    cat_change_counts: dict[str, int] = {}

    for i, (fid, title, author, publisher, rel_path, ext, size) in enumerate(rows, 1):
        path = BOOKS_ROOT / rel_path
        text = ""
        try:
            if ext == "epub":
                text = extract_epub_text(path)
            elif ext == "pdf":
                text = extract_pdf_text(path)
            elif ext == "txt":
                text = extract_txt(path)
            n_extract_ok += 1
        except FileNotFoundError:
            n_error += 1
        except Exception:
            n_error += 1

        # 用抽出的文本 + 原信息一起喂分类
        enriched_title = ((title or "") + " " + text).strip()
        c1, c2, subjs = classify(enriched_title, author, publisher, rel_path)

        if c1 != "other":
            cat_change_counts[c1] = cat_change_counts.get(c1, 0) + 1
            if not args.dry_run:
                conn.execute(
                    "UPDATE metadata SET category=?, category2=?, subjects=? WHERE file_id=?",
                    (c1, c2, json.dumps(subjs, ensure_ascii=False), fid),
                )
            n_changed += 1

        if i % LOG_EVERY == 0:
            elapsed = time.time() - t_start
            rate = i / elapsed
            eta = (len(rows) - i) / rate if rate > 0 else 0
            print(f"  [{i}/{len(rows)}] extract_ok={n_extract_ok} "
                  f"changed={n_changed} error={n_error} "
                  f"rate={rate:.1f}/s eta={eta/60:.1f}min", flush=True)
            if not args.dry_run:
                conn.commit()

    if not args.dry_run:
        conn.commit()
    conn.close()

    elapsed = time.time() - t_start
    print(f"\nDONE in {elapsed/60:.1f}min")
    print(f"  total:      {len(rows)}")
    print(f"  extract ok: {n_extract_ok}")
    print(f"  errors:     {n_error}")
    print(f"  reclassified: {n_changed} ({100*n_changed/len(rows):.1f}%)")
    print(f"  change by category:")
    for c, n in sorted(cat_change_counts.items(), key=lambda x: -x[1]):
        print(f"    {c:12s} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
