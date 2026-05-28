"""阶段 3：在线元数据补全 + 封面下载。

策略：
- 有 ISBN：先查豆瓣 isbn 页（中文书优势），失败 fallback Google Books
- 只有 title：先查豆瓣 search，再 Google Books
- 全部结果缓存到 lookups 表（query_key 唯一）
- 封面落 covers/<file_id>.online.jpg
- 限流：豆瓣 2s/req，Google Books 0.5s/req
- 断点续跑：跳过已有 cover 或 metadata.source 已经是 online 的
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests

from .paths import COVER_DIR

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.5 Safari/605.1.15"
)

DOUBAN_LAST = [0.0]
GOOGLE_LAST = [0.0]
DOUBAN_INTERVAL = 2.5
GOOGLE_INTERVAL = 0.4

# 豆瓣被风控后退避（全局）
DOUBAN_DISABLED_UNTIL = [0.0]
DOUBAN_FAIL_STREAK = [0]


def _throttle(last: list[float], interval: float):
    elapsed = time.time() - last[0]
    if elapsed < interval:
        time.sleep(interval - elapsed)
    last[0] = time.time()


def _get_cached(conn: sqlite3.Connection, key: str) -> dict | None:
    row = conn.execute(
        "SELECT response_json FROM lookups WHERE query_key = ?", (key,)
    ).fetchone()
    if row:
        return json.loads(row["response_json"])
    return None


def _cache(conn: sqlite3.Connection, key: str, provider: str, data: dict):
    conn.execute(
        "INSERT OR REPLACE INTO lookups (query_key, provider, response_json, fetched_at) "
        "VALUES (?, ?, ?, ?)",
        (key, provider, json.dumps(data, ensure_ascii=False), time.time()),
    )
    conn.commit()


def query_douban_isbn(isbn: str) -> dict | None:
    """爬豆瓣 isbn 页。返回标准化 dict 或 None。被风控时返回 {error:disabled}。"""
    if time.time() < DOUBAN_DISABLED_UNTIL[0]:
        return {"error": "disabled"}
    _throttle(DOUBAN_LAST, DOUBAN_INTERVAL)
    url = f"https://book.douban.com/isbn/{isbn}/"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=15, allow_redirects=True)
    except requests.RequestException as e:
        DOUBAN_FAIL_STREAK[0] += 1
        return {"error": str(e)}
    if r.status_code in (403, 429):
        DOUBAN_FAIL_STREAK[0] += 1
        # 连续 3 次封禁 → 关掉 30 分钟
        if DOUBAN_FAIL_STREAK[0] >= 3:
            DOUBAN_DISABLED_UNTIL[0] = time.time() + 1800
            print(f"  ! douban blocked, disabled for 30min", file=sys.stderr)
        return {"error": f"http {r.status_code}"}
    if r.status_code != 200:
        return {"error": f"http {r.status_code}"}
    DOUBAN_FAIL_STREAK[0] = 0

    html = r.text

    def find1(pattern, flags=re.S):
        m = re.search(pattern, html, flags)
        return m.group(1).strip() if m else None

    title = find1(r'<span\s+property="v:itemreviewed">([^<]+)</span>')
    if not title:
        return {"error": "not parsed"}

    # info 块里按 label 抓
    info_block = find1(r'<div id="info"[^>]*>(.+?)</div>')
    author = publisher = pubdate = None
    if info_block:
        def info_label(label):
            # 形如 "<span class=\"pl\">出版社:</span> 中信出版集团<br/>"
            m = re.search(rf'<span class="pl">\s*{label}[:：]\s*</span>([^<]+)<br', info_block)
            if m:
                return m.group(1).strip()
            # 形如 "<span><span class=\"pl\"> 作者</span>:...<a ...>X</a>...</span><br/>"
            m = re.search(
                rf'<span class="pl">\s*{label}\s*</span>\s*[:：]?\s*(.+?)</span>\s*<br',
                info_block, re.S,
            )
            if m:
                txt = re.sub(r"<[^>]+>", "/", m.group(1))
                txt = re.sub(r"\s+", " ", txt).strip(" /;")
                return txt or None
            return None

        author = info_label("作者")
        publisher = info_label("出版社")
        pubdate = info_label("出版年")

    # 简介：先找 "<span class=\"all hidden\">...展开全部</span>" 块
    summary = None
    # 整段 intro
    m = re.search(r'<h2>\s*<i>\s*内容简介.+?</h2>\s*<div class="indent">(.+?)</div>\s*</div>',
                  html, re.S)
    if m:
        # 在 indent 里找 "all hidden"，没有就用 "intro"
        block = m.group(1)
        mm = re.search(r'<span\s+class="all hidden"[^>]*>(.+?)</span>', block, re.S)
        if not mm:
            mm = re.search(r'<div class="intro"[^>]*>(.+?)</div>', block, re.S)
        if mm:
            summary = mm.group(1)
    if not summary:
        summary = find1(r'<span\s+class="all hidden"[^>]*>(.+?)</span>')
    if summary:
        # 去 <style>...</style> 段
        summary = re.sub(r'<style[^>]*>.*?</style>', '', summary, flags=re.S)
        # 把 <p>/<br> 转换行
        summary = re.sub(r'</p>\s*<p[^>]*>', '\n\n', summary)
        summary = re.sub(r'<br\s*/?>', '\n', summary)
        summary = re.sub(r'<[^>]+>', '', summary)
        summary = re.sub(r'\n{3,}', '\n\n', summary).strip()

    # 封面：rel="v:photo" 顺序不固定
    cover = find1(r'<img\b[^>]*?\bsrc="([^"]+)"[^>]*\brel="v:photo"')
    if not cover:
        cover = find1(r'<img\b[^>]*?\brel="v:photo"[^>]*?\bsrc="([^"]+)"')
    if not cover:
        cover = find1(r'id="mainpic".+?<img[^>]*src="([^"]+)"')

    tags_raw = find1(r'<div id="db-tags-section".+?<div class="indent">(.+?)</div>')
    tags = []
    if tags_raw:
        tags = re.findall(r">([^<>]+)</a>", tags_raw)
        tags = [t.strip() for t in tags if t.strip()]

    return {
        "title": title, "author": author, "publisher": publisher,
        "pubdate": pubdate, "summary": summary, "cover_url": cover,
        "tags": tags, "isbn": isbn, "_provider": "douban",
    }


def query_google_books_isbn(isbn: str) -> dict | None:
    _throttle(GOOGLE_LAST, GOOGLE_INTERVAL)
    url = "https://www.googleapis.com/books/v1/volumes"
    try:
        r = requests.get(url, params={"q": f"isbn:{isbn}"}, timeout=15)
    except requests.RequestException as e:
        return {"error": str(e)}
    if r.status_code != 200:
        return {"error": f"http {r.status_code}"}
    data = r.json()
    if data.get("totalItems", 0) == 0 or not data.get("items"):
        return None
    info = data["items"][0].get("volumeInfo", {})
    return {
        "title": info.get("title"),
        "author": "; ".join(info.get("authors", [])) or None,
        "publisher": info.get("publisher"),
        "pubdate": info.get("publishedDate"),
        "summary": info.get("description"),
        "cover_url": (info.get("imageLinks") or {}).get("thumbnail"),
        "tags": info.get("categories", []),
        "isbn": isbn,
        "_provider": "google_books",
    }


def query_google_books_title(title: str, author: str | None) -> dict | None:
    _throttle(GOOGLE_LAST, GOOGLE_INTERVAL)
    q = f'intitle:"{title}"'
    if author:
        q += f' inauthor:"{author.split(";")[0].strip()}"'
    try:
        r = requests.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": q, "maxResults": 1},
            timeout=15,
        )
    except requests.RequestException as e:
        return {"error": str(e)}
    if r.status_code != 200:
        return {"error": f"http {r.status_code}"}
    data = r.json()
    if not data.get("items"):
        return None
    info = data["items"][0].get("volumeInfo", {})
    isbn = None
    for ident in info.get("industryIdentifiers", []):
        if "ISBN" in ident.get("type", ""):
            isbn = ident.get("identifier")
            break
    return {
        "title": info.get("title"),
        "author": "; ".join(info.get("authors", [])) or None,
        "publisher": info.get("publisher"),
        "pubdate": info.get("publishedDate"),
        "summary": info.get("description"),
        "cover_url": (info.get("imageLinks") or {}).get("thumbnail"),
        "tags": info.get("categories", []),
        "isbn": isbn,
        "_provider": "google_books",
    }


def lookup_one(conn: sqlite3.Connection, isbn: str | None, title: str | None,
               author: str | None) -> dict | None:
    """按 isbn/title 查询，先缓存，缓存未命中按 douban→google 顺序拉。"""
    if isbn:
        key = f"isbn:{isbn}"
        cached = _get_cached(conn, key)
        if cached is not None:
            return cached if cached.get("title") else None
        result = query_douban_isbn(isbn)
        if result and not result.get("error") and result.get("title"):
            _cache(conn, key, "douban", result)
            return result
        douban_transient = bool(result and result.get("error") in ("disabled",))
        result = query_google_books_isbn(isbn)
        if result and not result.get("error") and result.get("title"):
            _cache(conn, key, "google_books", result)
            return result
        # 都是临时失败的话不要缓存
        if not douban_transient:
            _cache(conn, key, "none", {"title": None, "error": "not found"})
        return None

    if title:
        key = f"title:{title}|author:{author or ''}"
        cached = _get_cached(conn, key)
        if cached is not None:
            return cached if cached.get("title") else None
        result = query_google_books_title(title, author)
        if result and not result.get("error") and result.get("title"):
            _cache(conn, key, "google_books", result)
            return result
        _cache(conn, key, "none", {"title": None, "error": "not found"})
        return None

    return None


def download_cover(url: str, out_path: Path) -> bool:
    if not url:
        return False
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Referer": "https://book.douban.com/"},
                         timeout=20)
        if r.status_code == 200 and len(r.content) > 100:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(r.content)
            return True
    except requests.RequestException:
        return False
    return False


def lookup_all(conn: sqlite3.Connection, *, limit: int | None, force: bool) -> dict:
    """对 metadata 行做在线补全。"""
    stats = {"processed": 0, "matched": 0, "covers": 0, "miss": 0}

    where = "m.source IN ('embedded', 'filename')"
    if not force:
        where += " AND m.source != 'online'"

    q = f"""
        SELECT m.file_id, m.title, m.author, m.isbn, f.rel_path
        FROM metadata m
        JOIN files f ON f.id = m.file_id
        WHERE {where}
        ORDER BY (m.isbn IS NULL), m.confidence DESC, m.file_id
    """
    if limit:
        q += f" LIMIT {int(limit)}"

    rows = conn.execute(q).fetchall()
    total = len(rows)
    print(f"lookup: {total} candidates queued", file=sys.stderr)

    t0 = time.time()
    for i, row in enumerate(rows, 1):
        result = lookup_one(conn, row["isbn"], row["title"], row["author"])
        stats["processed"] += 1
        if not result:
            stats["miss"] += 1
        else:
            stats["matched"] += 1
            tags_json = json.dumps(result.get("tags") or [], ensure_ascii=False)
            conn.execute(
                """
                UPDATE metadata
                SET title=COALESCE(?, title),
                    author=COALESCE(?, author),
                    isbn=COALESCE(?, isbn),
                    publisher=COALESCE(?, publisher),
                    pubdate=COALESCE(?, pubdate),
                    tags=?,
                    source='online',
                    confidence=MAX(confidence, 0.95)
                WHERE file_id=?
                """,
                (result.get("title"), result.get("author"), result.get("isbn"),
                 result.get("publisher"), result.get("pubdate"),
                 tags_json, row["file_id"]),
            )
            # summary 写到一个独立的 sidecar 文件，免动 schema
            if result.get("summary"):
                sum_path = COVER_DIR / f"{row['file_id']}.summary.txt"
                sum_path.parent.mkdir(parents=True, exist_ok=True)
                sum_path.write_text(result["summary"], encoding="utf-8")
            # 封面
            cover_url = result.get("cover_url")
            if cover_url:
                cover_path = COVER_DIR / f"{row['file_id']}.online.jpg"
                if cover_path.exists() and not force:
                    stats["covers"] += 1
                elif download_cover(cover_url, cover_path):
                    stats["covers"] += 1
            conn.commit()

        if i % 20 == 0:
            dt = time.time() - t0
            print(
                f"  [{i:>5}/{total}] matched={stats['matched']} miss={stats['miss']} "
                f"covers={stats['covers']} ({i/dt:.1f}/s)",
                file=sys.stderr, flush=True,
            )

    conn.commit()
    return stats
