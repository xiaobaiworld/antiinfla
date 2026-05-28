"""阶段 2：本地元数据提取（嵌入式）。

只读。优先用 calibre 的 `ebook-meta` CLI（支持 EPUB/MOBI/AZW3/PDF/LIT/PRC/FB2 等），
失败再 fallback 到 ebooklib（EPUB）/ pypdf（PDF）/ 文件名解析。

封面落到 covers/<file_id>.jpg。

断点续跑：跳过已有 metadata 行的文件；--force 强制重抓。
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    from ebooklib import epub, ITEM_COVER, ITEM_IMAGE
    HAS_EBOOKLIB = True
except ImportError:
    HAS_EBOOKLIB = False

try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

from .paths import COVER_DIR, CALIBRE_EBOOK_META, HAS_CALIBRE

# calibre 处理的扩展名
CALIBRE_EXTS = {"epub", "mobi", "azw", "azw3", "azw4", "pdf", "lit", "prc", "fb2",
                "lrf", "rtf", "rb", "html", "htm", "txt", "docx"}

ISBN_RE = re.compile(r"\b(97[89][\d\-\s]{10,17}|\d{9}[\dXx])\b")


def _norm_isbn(s: str | None) -> str | None:
    if not s:
        return None
    digits = re.sub(r"[\s\-]", "", s)
    if len(digits) in (10, 13) and (digits[:-1].isdigit() and (digits[-1].isdigit() or digits[-1].lower() == "x")):
        return digits.upper()
    m = ISBN_RE.search(s)
    if m:
        d = re.sub(r"[\s\-]", "", m.group(1))
        if len(d) in (10, 13):
            return d.upper()
    return None


def extract_epub(path: Path, cover_out: Path) -> dict:
    """EPUB 元数据 + 封面。返回 dict。封面写到 cover_out。"""
    if not HAS_EBOOKLIB:
        return {"source": "none", "confidence": 0.0, "error": "ebooklib missing"}
    book = epub.read_epub(str(path), options={"ignore_ncx": True})

    def meta_first(ns, name):
        items = book.get_metadata(ns, name)
        return items[0][0] if items else None

    title = meta_first("DC", "title")
    creators = book.get_metadata("DC", "creator")
    author = "; ".join(c[0] for c in creators) if creators else None
    publisher = meta_first("DC", "publisher")
    language = meta_first("DC", "language")
    pubdate = meta_first("DC", "date")
    # ISBN 通常在 identifier 里
    isbn = None
    for ident in book.get_metadata("DC", "identifier"):
        val = ident[0]
        attrs = ident[1] or {}
        scheme = attrs.get("scheme", "").lower() or attrs.get("{http://www.idpf.org/2007/opf}scheme", "").lower()
        if "isbn" in scheme or _norm_isbn(val):
            isbn = _norm_isbn(val)
            if isbn:
                break

    # 封面提取：先找标记为 cover 的 item，其次扫 image 里名字含 cover 的
    cover_data = None
    cover_ext = "jpg"
    for item in book.get_items_of_type(ITEM_COVER):
        cover_data = item.get_content()
        if item.media_type:
            cover_ext = item.media_type.split("/")[-1].replace("jpeg", "jpg")
        break
    if not cover_data:
        for item in book.get_items_of_type(ITEM_IMAGE):
            name = (item.get_name() or "").lower()
            if "cover" in name:
                cover_data = item.get_content()
                if item.media_type:
                    cover_ext = item.media_type.split("/")[-1].replace("jpeg", "jpg")
                break

    if cover_data:
        cover_out.parent.mkdir(parents=True, exist_ok=True)
        cover_out.with_suffix(f".{cover_ext}").write_bytes(cover_data)

    confidence = 0.7
    if title and author:
        confidence = 0.85
    if isbn:
        confidence = 0.95

    return {
        "title": title,
        "author": author,
        "isbn": isbn,
        "publisher": publisher,
        "pubdate": pubdate,
        "language": language,
        "source": "embedded",
        "confidence": confidence,
    }


def extract_pdf(path: Path) -> dict:
    if not HAS_PYPDF:
        return {"source": "none", "confidence": 0.0, "error": "pypdf missing"}
    try:
        reader = PdfReader(str(path), strict=False)
    except Exception as e:
        return {"source": "none", "confidence": 0.0, "error": f"pdf read: {e}"}

    info = reader.metadata or {}
    title = (info.get("/Title") or "").strip() or None
    author = (info.get("/Author") or "").strip() or None
    isbn = None
    # 扫前 3 页找 ISBN
    try:
        for i, page in enumerate(reader.pages[:3]):
            text = page.extract_text() or ""
            isbn = _norm_isbn(text)
            if isbn:
                break
    except Exception:
        pass

    confidence = 0.0
    if title:
        confidence = 0.4
    if title and author:
        confidence = 0.6
    if isbn:
        confidence = 0.85

    return {
        "title": title,
        "author": author,
        "isbn": isbn,
        "source": "embedded" if title else "none",
        "confidence": confidence,
    }


def fallback_filename(name: str) -> dict:
    """文件名解析。形如 '书名 - 作者.epub' / '[作者]书名.pdf' / '书名_作者.mobi'。"""
    stem = re.sub(r"\.[a-z0-9]+$", "", name, flags=re.IGNORECASE)
    stem = re.sub(r"\(z-lib(?:rary)?\.org\)", "", stem, flags=re.IGNORECASE).strip()
    title = stem
    author = None
    m = re.match(r"^\[([^\]]+)\]\s*(.+)$", stem)
    if m:
        author = m.group(1).strip()
        title = m.group(2).strip()
    else:
        for sep in [" - ", "_-_", " — ", "—", "_"]:
            if sep in stem:
                parts = [p.strip() for p in stem.split(sep)]
                if len(parts) == 2 and parts[0] and parts[1]:
                    title, author = parts[0], parts[1]
                    break

    if not title:
        return {"source": "none", "confidence": 0.0}
    return {
        "title": title,
        "author": author,
        "source": "filename",
        "confidence": 0.3 if author else 0.2,
    }


def extract_via_calibre(path: Path, cover_out: Path) -> dict:
    """调 calibre 的 ebook-meta。返回标准化 dict。"""
    if not HAS_CALIBRE:
        return {"source": "none", "confidence": 0.0, "error": "no calibre"}
    cover_out.parent.mkdir(parents=True, exist_ok=True)
    cover_path = cover_out.with_suffix(".jpg")
    try:
        proc = subprocess.run(
            [CALIBRE_EBOOK_META, str(path), f"--get-cover={cover_path}"],
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return {"source": "none", "confidence": 0.0, "error": "calibre timeout"}
    except OSError as e:
        return {"source": "none", "confidence": 0.0, "error": f"calibre spawn: {e}"}

    if proc.returncode != 0 and not proc.stdout:
        return {"source": "none", "confidence": 0.0,
                "error": f"calibre rc={proc.returncode}: {proc.stderr[:200]}"}

    meta = {}
    for line in proc.stdout.splitlines():
        m = re.match(r"^([A-Za-z()\s/]+?)\s+:\s+(.+)$", line)
        if m:
            label = m.group(1).strip()
            value = m.group(2).strip()
            meta[label] = value

    title = meta.get("Title") or None
    if not title:
        return {"source": "none", "confidence": 0.0, "error": "no title in output"}

    raw_authors = meta.get("Author(s)") or ""
    # 形如 "Author1 [last, first] & Author2 [last, first]"
    authors = []
    for a in raw_authors.split(" & "):
        a = re.sub(r"\s*\[[^\]]*\]\s*$", "", a).strip()
        if a and a.lower() != "unknown":
            authors.append(a)
    author = "; ".join(authors) or None

    isbn = None
    identifiers = meta.get("Identifiers") or ""
    m = re.search(r"isbn:([0-9Xx]{10,13})", identifiers)
    if m:
        isbn = m.group(1).upper()

    pubdate = meta.get("Published") or None
    publisher = meta.get("Publisher") or None
    language = meta.get("Languages") or None
    if language and "," in language:
        language = language.split(",")[0].strip()

    tags = []
    if meta.get("Tags"):
        tags = [t.strip() for t in meta["Tags"].split(",") if t.strip()]

    summary = meta.get("Comments") or None
    if summary:
        # ebook-meta 用 HTML 写 Comments，去标签
        summary = re.sub(r"<[^>]+>", "", summary).strip()
        summary = re.sub(r"\s{2,}", " ", summary)

    confidence = 0.8
    if title and author:
        confidence = 0.9
    if isbn:
        confidence = 0.95

    out = {
        "title": title, "author": author, "isbn": isbn,
        "publisher": publisher, "pubdate": pubdate, "language": language,
        "tags": tags, "summary": summary,
        "source": "embedded", "confidence": confidence,
    }
    return out


def extract_one(path: Path, ext: str, file_id: int) -> dict:
    cover_out = COVER_DIR / f"{file_id}"
    # 先 calibre（支持的格式）
    if HAS_CALIBRE and ext in CALIBRE_EXTS:
        try:
            meta = extract_via_calibre(path, cover_out)
            if meta.get("title"):
                # 抽出来的 summary 也落 sidecar
                if meta.get("summary"):
                    sp = COVER_DIR / f"{file_id}.summary.txt"
                    sp.parent.mkdir(parents=True, exist_ok=True)
                    sp.write_text(meta["summary"], encoding="utf-8")
                return meta
        except Exception as e:
            print(f"  calibre err {path.name}: {e}", file=sys.stderr)
    # fallback：纯 Python 解析
    if ext == "epub":
        try:
            meta = extract_epub(path, cover_out)
            if meta.get("title"):
                return meta
        except Exception as e:
            print(f"  epub err {path.name}: {e}", file=sys.stderr)
    elif ext == "pdf":
        try:
            meta = extract_pdf(path)
            if meta.get("title"):
                return meta
        except Exception as e:
            print(f"  pdf err {path.name}: {e}", file=sys.stderr)
    return fallback_filename(path.name)


# EPUB/MOBI/AZW3 优先（真正的电子书），PDF 后面跑（数量多但很多是扫描件/报告/PPT）
_EXT_PRIORITY = {"epub": 1, "mobi": 2, "azw3": 3, "azw": 4, "azw4": 5,
                 "fb2": 6, "prc": 7, "lit": 8,
                 "pdf": 10, "djvu": 11, "chm": 12, "doc": 13, "docx": 14, "txt": 15}


def extract_all(conn: sqlite3.Connection, root: Path, *, exts: list[str], limit: int | None,
                force: bool, workers: int = 4) -> dict:
    """对 ext 在 exts 中的 files 行做提取。并行抽以加速。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    stats = {"processed": 0, "ok": 0, "fallback": 0, "skipped": 0, "errors": 0}

    placeholders = ",".join("?" for _ in exts)
    q = f"""
        SELECT f.id, f.rel_path, f.ext, f.name
        FROM files f
        LEFT JOIN metadata m ON m.file_id = f.id
        WHERE f.ext IN ({placeholders})
          AND f.kind = 'book'
          {'' if force else 'AND m.file_id IS NULL'}
    """
    if limit:
        q += f" LIMIT {int(limit)}"

    rows = conn.execute(q, exts).fetchall()
    # 按 ext 优先级 + file_id 排序（先真正的电子书）
    rows = sorted(rows, key=lambda r: (_EXT_PRIORITY.get(r["ext"], 99), r["id"]))
    total = len(rows)
    print(f"extract: {total} files queued (exts={','.join(exts)}, workers={workers})",
          file=sys.stderr)

    def work(row):
        path = root / row["rel_path"]
        try:
            if not path.exists():
                return row, None, "missing"
            meta = extract_one(path, row["ext"], row["id"])
            return row, meta, None
        except OSError as e:
            # SMB 断线 / 权限等 → 软错误，不要 crash 整个流水线
            return row, None, f"oserror: {e}"
        except Exception as e:
            return row, None, str(e)

    t0 = time.time()
    pending = 0
    consecutive_errors = 0
    abort_threshold = 50  # 连续 N 个错误 → 认为 NAS 断线，提前结束阶段
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(work, r) for r in rows]
        for i, fut in enumerate(as_completed(futures), 1):
            row, meta, err = fut.result()
            if err:
                if err == "missing":
                    stats["errors"] += 1
                elif err.startswith("oserror:"):
                    stats["errors"] += 1
                    consecutive_errors += 1
                    if consecutive_errors == 1 or consecutive_errors % 10 == 0:
                        print(f"  ! oserror×{consecutive_errors} ({row['rel_path']}: {err[:80]})",
                              file=sys.stderr)
                    if consecutive_errors >= abort_threshold:
                        print(f"  !! {abort_threshold} consecutive oserrors — NAS likely "
                              f"offline, aborting extract phase early", file=sys.stderr)
                        # 取消剩余任务，跳出
                        for f in futures:
                            f.cancel()
                        break
                else:
                    print(f"  ! {row['rel_path']}: {err}", file=sys.stderr)
                    stats["errors"] += 1
                continue
            consecutive_errors = 0

            stats["processed"] += 1
            src = meta.get("source")
            if src == "embedded":
                stats["ok"] += 1
            elif src == "filename":
                stats["fallback"] += 1
            else:
                stats["skipped"] += 1

            conn.execute(
                """
                INSERT INTO metadata
                    (file_id, title, author, isbn, publisher, pubdate, language, tags,
                     source, confidence, extracted_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(file_id) DO UPDATE SET
                    title=excluded.title, author=excluded.author, isbn=excluded.isbn,
                    publisher=excluded.publisher, pubdate=excluded.pubdate,
                    language=excluded.language, tags=excluded.tags,
                    source=excluded.source, confidence=excluded.confidence,
                    extracted_at=excluded.extracted_at
                """,
                (
                    row["id"], meta.get("title"), meta.get("author"), meta.get("isbn"),
                    meta.get("publisher"), meta.get("pubdate"), meta.get("language"),
                    json.dumps(meta.get("tags") or [], ensure_ascii=False),
                    meta.get("source", "none"), float(meta.get("confidence", 0.0)),
                    time.time(),
                ),
            )
            pending += 1
            if pending >= 100:
                conn.commit()
                pending = 0
            if i % 100 == 0:
                dt = time.time() - t0
                print(
                    f"  [{i:>5}/{total}] ok={stats['ok']} fb={stats['fallback']} "
                    f"err={stats['errors']} ({i/dt:.1f}/s)",
                    file=sys.stderr, flush=True,
                )
    conn.commit()
    return stats
