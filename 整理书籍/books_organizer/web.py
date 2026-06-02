"""阶段 5：在线阅读站（Flask）。

  python3 -m books_organizer web --port 8765

特性：
- 首页：封面网格，精选/筛选/搜索；"继续阅读"区（登录用户）
- 书籍详情：评分、进度、相关书、简介
- 在线阅读：EPUB / PDF / TXT / DOCX / MOBI / AZW3 全部支持，自动保存进度
- 用户系统：localStorage UUID，匿名，可设置名字/合并账号/导出导入
- 书籍上传：拖拽或文件选择，SHA256 去重
- 相关书推荐：同二级分类 + LLM fine_tags Jaccard 相似度
"""
from __future__ import annotations

import datetime
import hashlib
import json
import mimetypes
import os
import random
import sqlite3
import subprocess
import threading
import time
import uuid as uuid_module
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template_string, request, send_file

from . import index_fields
from .admin import admin_bp, ensure_default_source, get_source_path, invalidate_source_cache  # noqa: F401
from .paths import BOOKS_ROOT as ROOT, DB_PATH, COVER_DIR, HAS_CALIBRE, CALIBRE_EBOOK_META, UPLOAD_DIR
from .user_db import get_user_db, resolve_user

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB
app.register_blueprint(admin_bp)

ALLOWED_UPLOAD_EXTS = {"epub", "pdf", "txt", "docx", "doc", "mobi", "azw3", "azw"}

_related_cache: dict = {}
_related_lock = threading.Lock()
RELATED_CACHE_TTL = 300


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


PLACEHOLDER_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 200 280'>"
    "<rect width='200' height='280' fill='#e8e6df'/>"
    "<text x='100' y='140' text-anchor='middle' fill='#888' "
    "font-family='sans-serif' font-size='14'>无封面</text>"
    "</svg>"
).encode("utf-8")


@app.route("/cover/<int:file_id>")
def cover(file_id: int):
    online = COVER_DIR / f"{file_id}.online.jpg"
    if online.exists():
        return send_file(online.resolve(), mimetype="image/jpeg")
    for ext in ("jpg", "jpeg", "png", "webp"):
        p = COVER_DIR / f"{file_id}.{ext}"
        if p.exists():
            return send_file(p.resolve(), mimetype=f"image/{ext.replace('jpg','jpeg')}")
    return Response(PLACEHOLDER_SVG, mimetype="image/svg+xml")


def _resolve_book_path(rel_path: str, source_id) -> Path:
    if source_id is None:
        return ROOT / rel_path
    p = get_source_path(source_id)
    return (p / rel_path) if p else (ROOT / rel_path)


@app.route("/file/<int:file_id>")
def raw_file(file_id: int):
    conn = get_db()
    row = conn.execute("SELECT rel_path, ext, source_id FROM files WHERE id = ?", (file_id,)).fetchone()
    if not row:
        abort(404)
    path = _resolve_book_path(row["rel_path"], row["source_id"])
    if not path.exists():
        abort(404)
    mime, _ = mimetypes.guess_type(path.name)
    if not mime:
        mime = "application/octet-stream"
    return send_file(path.resolve(), mimetype=mime, as_attachment=False,
                     download_name=path.name, conditional=True)


# ── Books API ──────────────────────────────────────────────────────────────────

@app.route("/api/books")
def api_books():
    conn = get_db()
    args = request.args
    q = args.get("q", "").strip()
    category = args.get("category", "").strip()
    author = args.get("author", "").strip()
    ext = args.get("ext", "").strip()
    sort = args.get("sort", "title")
    page = max(1, int(args.get("page", 1)))
    per_page = min(120, max(10, int(args.get("per_page", 40))))

    where = ["m.title IS NOT NULL", "m.title != ''",
             "(m.cluster_role = 'primary' OR m.cluster_role IS NULL)"]
    params: list = []
    if q:
        where.append("(m.title LIKE ? OR m.author LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if author:
        where.append("m.author LIKE ?")
        params.append(f"%{author}%")
    if ext:
        where.append("f.ext = ?")
        params.append(ext)
    if category:
        where.append("m.category = ?")
        params.append(category)
    category2 = args.get("category2", "").strip()
    if category2:
        where.append("m.category2 = ?")
        params.append(category2)
    subject = args.get("subject", "").strip()
    if subject:
        where.append("m.subjects LIKE ?")
        params.append(f'%"{subject}"%')
    decade = args.get("decade", "").strip()
    if decade.isdigit():
        d = int(decade)
        where.append("m.pub_year >= ? AND m.pub_year < ?")
        params += [d, d + 10]

    order = {
        "title": "m.title ASC",
        "author": "m.author ASC",
        "id": "f.id DESC",
        "confidence": "m.confidence DESC",
        "pinyin": "COALESCE(NULLIF(m.title_sort, ''), m.title) ASC",
        "pub_year_desc": "(m.pub_year IS NULL), m.pub_year DESC, m.title ASC",
        "pub_year_asc": "(m.pub_year IS NULL), m.pub_year ASC, m.title ASC",
    }.get(sort, "m.title ASC")

    where_sql = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM files f JOIN metadata m ON m.file_id=f.id WHERE {where_sql}",
        params,
    ).fetchone()[0]
    offset = (page - 1) * per_page
    rows = conn.execute(
        f"""SELECT f.id, f.ext, f.rel_path, m.title, m.author, m.publisher,
                   m.confidence, m.tags
            FROM files f JOIN metadata m ON m.file_id=f.id
            WHERE {where_sql}
            ORDER BY {order}
            LIMIT ? OFFSET ?""",
        params + [per_page, offset],
    ).fetchall()
    return jsonify({
        "total": total, "page": page, "per_page": per_page,
        "books": [dict(r) for r in rows],
    })


@app.route("/api/random")
def api_random():
    conn = get_db()
    row = conn.execute(
        "SELECT f.id FROM files f JOIN metadata m ON m.file_id=f.id "
        "WHERE m.title IS NOT NULL AND m.title!='' "
        "AND (m.cluster_role='primary' OR m.cluster_role IS NULL) "
        "ORDER BY RANDOM() LIMIT 1"
    ).fetchone()
    if not row:
        abort(404)
    return jsonify({"id": row["id"]})


@app.route("/api/featured")
def api_featured():
    """每日精选：business 8本, literature 6本, humanities 6本, other 4本。
    seed 参数可覆盖日期种子，用于"换一批"功能。"""
    seed = request.args.get("seed") or datetime.date.today().isoformat()
    rng = random.Random(seed)

    conn = get_db()
    primary_filter = "(m.cluster_role = 'primary' OR m.cluster_role IS NULL)"
    base_where = f"m.title IS NOT NULL AND m.title != '' AND {primary_filter}"

    distribution = [
        ("business", 8),
        ("literature", 6),
        ("humanities", 6),
    ]
    other_count = 4

    selected: list[dict] = []
    used_ids: set[int] = set()

    for cat, target_n in distribution:
        rows = conn.execute(
            f"""SELECT f.id, f.ext, m.title, m.author, m.confidence, m.pub_year
                FROM files f JOIN metadata m ON m.file_id=f.id
                WHERE {base_where} AND m.category = ?
                ORDER BY (m.pub_year IS NULL), m.pub_year DESC, m.confidence DESC
                LIMIT ?""",
            (cat, target_n * 3),
        ).fetchall()
        pool = [dict(r) for r in rows]
        chosen = pool if len(pool) <= target_n else rng.sample(pool, target_n)
        for b in chosen:
            used_ids.add(b["id"])
            selected.append(b)

    already_cats = tuple(c for c, _ in distribution)
    placeholders = ",".join("?" * len(already_cats))
    other_rows = conn.execute(
        f"""SELECT f.id, f.ext, m.title, m.author, m.confidence, m.pub_year
            FROM files f JOIN metadata m ON m.file_id=f.id
            WHERE {base_where} AND (m.category NOT IN ({placeholders}) OR m.category IS NULL)
            ORDER BY (m.pub_year IS NULL), m.pub_year DESC, m.confidence DESC
            LIMIT ?""",
        list(already_cats) + [other_count * 3],
    ).fetchall()
    other_pool = [dict(r) for r in other_rows if r["id"] not in used_ids]
    other_chosen = other_pool if len(other_pool) <= other_count else rng.sample(other_pool, other_count)
    selected.extend(other_chosen)
    rng.shuffle(selected)

    for b in selected:
        b.pop("pub_year", None)

    return jsonify({"books": selected, "total": len(selected)})


@app.route("/api/facets")
def api_facets():
    conn = get_db()
    primary_filter = "(m.cluster_role = 'primary' OR m.cluster_role IS NULL)"
    exts = [r["ext"] for r in conn.execute(
        f"SELECT f.ext, COUNT(*) n FROM files f JOIN metadata m ON m.file_id=f.id "
        f"WHERE m.title IS NOT NULL AND m.title!='' AND {primary_filter} "
        f"GROUP BY f.ext ORDER BY n DESC"
    )]
    authors = [r["author"] for r in conn.execute(
        f"SELECT m.author, COUNT(*) n FROM metadata m WHERE m.author IS NOT NULL "
        f"AND m.author != '' AND {primary_filter} "
        f"GROUP BY m.author ORDER BY n DESC LIMIT 80"
    )]
    rows = conn.execute(
        f"SELECT m.category, m.category2, m.subjects, COUNT(*) n FROM metadata m "
        f"WHERE m.category IS NOT NULL AND {primary_filter} "
        f"GROUP BY m.category, m.category2, m.subjects"
    ).fetchall()
    tree: dict = {}
    for r in rows:
        c1, c2, n = r["category"], r["category2"], r["n"]
        node = tree.setdefault(c1, {"n": 0, "subs": {}})
        node["n"] += n
        if not c2:
            continue
        sub_node = node["subs"].setdefault(c2, {"n": 0, "subjects": {}})
        sub_node["n"] += n
        if r["subjects"]:
            try:
                for s in json.loads(r["subjects"])[:6]:
                    if not s:
                        continue
                    sub_node["subjects"][s] = sub_node["subjects"].get(s, 0) + n
            except (ValueError, TypeError):
                pass

    def _build_subs(subs_dict):
        out = []
        for sk, sv in subs_dict.items():
            subjects_top = sorted(
                ({"key": kk, "n": vv} for kk, vv in sv["subjects"].items()
                 if vv >= 2 and kk != sk),
                key=lambda x: -x["n"],
            )[:30]
            out.append({"key": sk, "n": sv["n"], "subjects": subjects_top})
        return sorted(out, key=lambda x: -x["n"])

    cats = sorted(
        [{"key": k, "n": v["n"], "subs": _build_subs(v["subs"])}
         for k, v in tree.items()],
        key=lambda x: -x["n"],
    )
    decades_rows = conn.execute(
        f"SELECT (m.pub_year / 10) * 10 AS decade, COUNT(*) n FROM metadata m "
        f"WHERE m.pub_year IS NOT NULL AND {primary_filter} "
        f"GROUP BY decade ORDER BY decade DESC"
    ).fetchall()
    decades = [{"key": r["decade"], "n": r["n"]} for r in decades_rows if r["decade"]]

    return jsonify({
        "exts": exts, "authors": authors, "categories": cats, "decades": decades,
    })


@app.route("/api/book/<int:file_id>")
def api_book(file_id: int):
    conn = get_db()
    row = conn.execute(
        """SELECT f.id, f.rel_path, f.name, f.ext, f.size,
                  m.title, m.author, m.isbn, m.publisher, m.pubdate, m.tags, m.confidence,
                  m.cluster_key, m.cluster_role, m.primary_file_id,
                  m.category, m.category2, m.subjects, m.summary
           FROM files f JOIN metadata m ON m.file_id=f.id
           WHERE f.id = ?""", (file_id,)
    ).fetchone()
    if not row:
        abort(404)
    data = dict(row)
    if not data.get("summary"):
        sum_path = COVER_DIR / f"{file_id}.summary.txt"
        if sum_path.exists():
            data["summary"] = sum_path.read_text(encoding="utf-8")

    variants = []
    if data.get("cluster_key"):
        for r in conn.execute(
            """SELECT f.id, f.ext, f.size, m.publisher, m.pubdate, m.cluster_role
               FROM files f JOIN metadata m ON m.file_id=f.id
               WHERE m.cluster_key = ? AND f.id != ?
               ORDER BY m.cluster_role, f.ext""",
            (data["cluster_key"], file_id),
        ):
            variants.append(dict(r))
    data["variants"] = variants
    return jsonify(data)


@app.route("/api/book/<int:file_id>/related")
def api_related(file_id: int):
    with _related_lock:
        cached = _related_cache.get(file_id)
        if cached and (time.time() - cached["ts"] < RELATED_CACHE_TTL):
            return jsonify(cached["data"])

    conn = get_db()
    row = conn.execute(
        "SELECT m.category2, m.fine_tags FROM metadata m WHERE m.file_id=?",
        (file_id,)
    ).fetchone()
    if not row:
        return jsonify({"related": []})

    related: list[dict] = []
    seen_ids: set[int] = {file_id}

    if row["category2"]:
        rows = conn.execute(
            """SELECT f.id, f.ext, m.title, m.author, m.confidence
               FROM files f JOIN metadata m ON m.file_id=f.id
               WHERE m.category2=? AND f.id!=? AND m.title IS NOT NULL AND m.title!=''
               AND (m.cluster_role='primary' OR m.cluster_role IS NULL)
               ORDER BY m.confidence DESC LIMIT 20""",
            (row["category2"], file_id)
        ).fetchall()
        for r in rows:
            if r["id"] not in seen_ids:
                related.append({
                    "id": r["id"], "title": r["title"],
                    "author": r["author"], "ext": r["ext"],
                })
                seen_ids.add(r["id"])

    if row["fine_tags"]:
        try:
            my_tags = set(json.loads(row["fine_tags"]))
        except (ValueError, TypeError):
            my_tags = set()
        if my_tags:
            tag_rows = conn.execute(
                """SELECT f.id, f.ext, m.title, m.author, m.fine_tags
                   FROM files f JOIN metadata m ON m.file_id=f.id
                   WHERE m.fine_tags IS NOT NULL AND f.id!=?
                   AND m.title IS NOT NULL AND m.title!=''
                   AND (m.cluster_role='primary' OR m.cluster_role IS NULL)
                   LIMIT 2000""",
                (file_id,)
            ).fetchall()
            scored = []
            for r in tag_rows:
                try:
                    other_tags = set(json.loads(r["fine_tags"]))
                    inter = my_tags & other_tags
                    union = my_tags | other_tags
                    j = len(inter) / len(union) if union else 0
                    if j > 0:
                        scored.append((j, dict(r)))
                except (ValueError, TypeError):
                    pass
            scored.sort(key=lambda x: -x[0])
            for _, r in scored[:15]:
                if r["id"] not in seen_ids:
                    related.append({
                        "id": r["id"], "title": r["title"],
                        "author": r["author"], "ext": r["ext"],
                    })
                    seen_ids.add(r["id"])

    result = {"related": related[:10]}
    with _related_lock:
        _related_cache[file_id] = {"ts": time.time(), "data": result}

    return jsonify(result)


# ── User API ───────────────────────────────────────────────────────────────────

@app.route("/api/user/init", methods=["POST"])
def api_user_init():
    data = request.get_json(silent=True) or {}
    user_id = (data.get("id") or "").strip() or str(uuid_module.uuid4())
    now = time.time()
    conn = get_user_db()
    existing = conn.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
    if existing:
        conn.execute("UPDATE users SET last_seen=? WHERE id=?", (now, user_id))
        conn.commit()
        return jsonify({"id": user_id, "created": False})
    conn.execute(
        "INSERT INTO users(id,name,created_at,last_seen) VALUES(?,?,?,?)",
        (user_id, None, now, now)
    )
    conn.commit()
    return jsonify({"id": user_id, "created": True})


@app.route("/api/user/<user_id>")
def api_user_get(user_id: str):
    conn = get_user_db()
    uid = resolve_user(conn, user_id)
    row = conn.execute(
        "SELECT id, name, created_at, last_seen FROM users WHERE id=?", (uid,)
    ).fetchone()
    if not row:
        abort(404)
    conn.execute("UPDATE users SET last_seen=? WHERE id=?", (time.time(), uid))
    conn.commit()
    return jsonify(dict(row))


@app.route("/api/user/<user_id>/name", methods=["PUT"])
def api_user_name(user_id: str):
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()[:100]
    conn = get_user_db()
    uid = resolve_user(conn, user_id)
    conn.execute("UPDATE users SET name=? WHERE id=?", (name or None, uid))
    conn.commit()
    return jsonify({"ok": True})


@app.route("/api/user/<user_id>/merge", methods=["POST"])
def api_user_merge(user_id: str):
    """Absorb other_id into user_id."""
    data = request.get_json(silent=True) or {}
    other_id = (data.get("other_id") or "").strip()
    if not other_id or other_id == user_id:
        return jsonify({"error": "invalid other_id"}), 400
    conn = get_user_db()
    uid = resolve_user(conn, user_id)
    oid = resolve_user(conn, other_id)
    if uid == oid:
        return jsonify({"ok": True, "note": "already same user"})
    now = time.time()
    for table, col in [("reading_history", "user_id"), ("bookmarks", "user_id"),
                       ("notes", "user_id"), ("ratings", "user_id")]:
        conn.execute(f"UPDATE OR IGNORE {table} SET {col}=? WHERE {col}=?", (uid, oid))
        conn.execute(f"DELETE FROM {table} WHERE {col}=?", (oid,))
    conn.execute(
        "INSERT OR REPLACE INTO user_aliases(alias_id,primary_id,merged_at) VALUES(?,?,?)",
        (oid, uid, now)
    )
    conn.execute("UPDATE users SET merged_into=? WHERE id=?", (uid, oid))
    conn.commit()
    return jsonify({"ok": True})


@app.route("/api/user/<user_id>/history", methods=["POST"])
def api_history_post(user_id: str):
    data = request.get_json(silent=True) or {}
    book_id = data.get("book_id")
    if not book_id:
        return jsonify({"error": "book_id required"}), 400
    progress = max(0.0, min(1.0, float(data.get("progress_pct", 0))))
    position = (data.get("last_position") or "")[:500]
    delta = int(data.get("delta_sec", 0))
    now = time.time()
    conn = get_user_db()
    uid = resolve_user(conn, user_id)
    ex = conn.execute(
        "SELECT id, total_time_sec FROM reading_history WHERE user_id=? AND book_id=?",
        (uid, book_id)
    ).fetchone()
    if ex:
        conn.execute(
            "UPDATE reading_history SET last_read_at=?,progress_pct=?,last_position=?,total_time_sec=? WHERE id=?",
            (now, progress, position, (ex["total_time_sec"] or 0) + delta, ex["id"])
        )
    else:
        conn.execute(
            "INSERT INTO reading_history(user_id,book_id,started_at,last_read_at,progress_pct,last_position,total_time_sec) VALUES(?,?,?,?,?,?,?)",
            (uid, book_id, now, now, progress, position, delta)
        )
    conn.commit()
    return jsonify({"ok": True})


@app.route("/api/user/<user_id>/history")
def api_history_get(user_id: str):
    conn = get_user_db()
    uid = resolve_user(conn, user_id)
    limit = min(50, int(request.args.get("limit", 20)))
    rows = conn.execute(
        "SELECT book_id, progress_pct, last_read_at, last_position "
        "FROM reading_history WHERE user_id=? ORDER BY last_read_at DESC LIMIT ?",
        (uid, limit)
    ).fetchall()
    bconn = get_db()
    result = []
    for r in rows:
        br = bconn.execute(
            "SELECT f.id, f.ext, m.title, m.author FROM files f JOIN metadata m ON m.file_id=f.id WHERE f.id=?",
            (r["book_id"],)
        ).fetchone()
        if br:
            result.append({
                "book_id": r["book_id"], "title": br["title"],
                "author": br["author"], "ext": br["ext"],
                "progress_pct": r["progress_pct"],
                "last_read_at": r["last_read_at"],
                "last_position": r["last_position"],
            })
    return jsonify({"history": result})


@app.route("/api/user/<user_id>/history/<int:book_id>")
def api_history_book(user_id: str, book_id: int):
    conn = get_user_db()
    uid = resolve_user(conn, user_id)
    row = conn.execute(
        "SELECT progress_pct, last_position, last_read_at, total_time_sec "
        "FROM reading_history WHERE user_id=? AND book_id=?",
        (uid, book_id)
    ).fetchone()
    if not row:
        return jsonify(None)
    return jsonify(dict(row))


@app.route("/api/user/<user_id>/bookmark", methods=["POST"])
def api_bookmark_add(user_id: str):
    data = request.get_json(silent=True) or {}
    book_id = data.get("book_id")
    if not book_id:
        return jsonify({"error": "book_id required"}), 400
    conn = get_user_db()
    uid = resolve_user(conn, user_id)
    conn.execute(
        "INSERT INTO bookmarks(user_id,book_id,position,label,color,created_at) VALUES(?,?,?,?,?,?)",
        (uid, book_id, (data.get("position") or "")[:500],
         (data.get("label") or "")[:200],
         (data.get("color") or "orange")[:20], time.time())
    )
    conn.commit()
    bm_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    return jsonify({"id": bm_id})


@app.route("/api/user/<user_id>/bookmarks/<int:book_id>")
def api_bookmarks_get(user_id: str, book_id: int):
    conn = get_user_db()
    uid = resolve_user(conn, user_id)
    rows = conn.execute(
        "SELECT id, position, label, color, created_at FROM bookmarks "
        "WHERE user_id=? AND book_id=? ORDER BY created_at",
        (uid, book_id)
    ).fetchall()
    return jsonify({"bookmarks": [dict(r) for r in rows]})


@app.route("/api/user/<user_id>/bookmark/<int:bm_id>", methods=["DELETE"])
def api_bookmark_delete(user_id: str, bm_id: int):
    conn = get_user_db()
    uid = resolve_user(conn, user_id)
    conn.execute("DELETE FROM bookmarks WHERE id=? AND user_id=?", (bm_id, uid))
    conn.commit()
    return jsonify({"ok": True})


@app.route("/api/user/<user_id>/note", methods=["POST"])
def api_note_add(user_id: str):
    data = request.get_json(silent=True) or {}
    book_id = data.get("book_id")
    if not book_id:
        return jsonify({"error": "book_id required"}), 400
    now = time.time()
    conn = get_user_db()
    uid = resolve_user(conn, user_id)
    note_id = data.get("id")
    if note_id:
        conn.execute(
            "UPDATE notes SET text=?, updated_at=? WHERE id=? AND user_id=?",
            ((data.get("text") or "")[:10000], now, note_id, uid)
        )
        conn.commit()
        return jsonify({"id": note_id})
    conn.execute(
        "INSERT INTO notes(user_id,book_id,position,text,created_at,updated_at) VALUES(?,?,?,?,?,?)",
        (uid, book_id, (data.get("position") or "")[:500],
         (data.get("text") or "")[:10000], now, now)
    )
    conn.commit()
    note_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    return jsonify({"id": note_id})


@app.route("/api/user/<user_id>/notes/<int:book_id>")
def api_notes_get(user_id: str, book_id: int):
    conn = get_user_db()
    uid = resolve_user(conn, user_id)
    rows = conn.execute(
        "SELECT id, position, text, created_at, updated_at FROM notes "
        "WHERE user_id=? AND book_id=? ORDER BY created_at",
        (uid, book_id)
    ).fetchall()
    return jsonify({"notes": [dict(r) for r in rows]})


@app.route("/api/user/<user_id>/note/<int:note_id>", methods=["DELETE"])
def api_note_delete(user_id: str, note_id: int):
    conn = get_user_db()
    uid = resolve_user(conn, user_id)
    conn.execute("DELETE FROM notes WHERE id=? AND user_id=?", (note_id, uid))
    conn.commit()
    return jsonify({"ok": True})


@app.route("/api/user/<user_id>/rating", methods=["POST"])
def api_rating_post(user_id: str):
    data = request.get_json(silent=True) or {}
    book_id = data.get("book_id")
    rating = data.get("rating")
    if not book_id or rating is None:
        return jsonify({"error": "book_id and rating required"}), 400
    rating = max(1, min(5, int(rating)))
    conn = get_user_db()
    uid = resolve_user(conn, user_id)
    conn.execute(
        "INSERT OR REPLACE INTO ratings(user_id,book_id,rating,review,created_at) VALUES(?,?,?,?,?)",
        (uid, book_id, rating, (data.get("review") or "")[:2000], time.time())
    )
    conn.commit()
    return jsonify({"ok": True})


@app.route("/api/user/<user_id>/export")
def api_user_export(user_id: str):
    conn = get_user_db()
    uid = resolve_user(conn, user_id)
    user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    export_data = {
        "exported_at": time.time(),
        "user": dict(user) if user else {},
        "history": [dict(r) for r in conn.execute(
            "SELECT * FROM reading_history WHERE user_id=?", (uid,))],
        "bookmarks": [dict(r) for r in conn.execute(
            "SELECT * FROM bookmarks WHERE user_id=?", (uid,))],
        "notes": [dict(r) for r in conn.execute(
            "SELECT * FROM notes WHERE user_id=?", (uid,))],
        "ratings": [dict(r) for r in conn.execute(
            "SELECT * FROM ratings WHERE user_id=?", (uid,))],
    }
    return Response(
        json.dumps(export_data, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=books_{uid[:8]}.json"},
    )


@app.route("/api/user/<user_id>/import", methods=["POST"])
def api_user_import(user_id: str):
    data = request.get_json(silent=True) or {}
    conn = get_user_db()
    uid = resolve_user(conn, user_id)
    now = time.time()
    imported = {"history": 0, "bookmarks": 0, "notes": 0, "ratings": 0}
    for h in (data.get("history") or []):
        try:
            conn.execute(
                "INSERT OR IGNORE INTO reading_history(user_id,book_id,started_at,last_read_at,progress_pct,last_position,total_time_sec) VALUES(?,?,?,?,?,?,?)",
                (uid, h["book_id"], h.get("started_at", now), h.get("last_read_at", now),
                 h.get("progress_pct", 0), h.get("last_position", ""), h.get("total_time_sec", 0))
            )
            imported["history"] += 1
        except Exception:
            pass
    for b in (data.get("bookmarks") or []):
        try:
            conn.execute(
                "INSERT INTO bookmarks(user_id,book_id,position,label,created_at) VALUES(?,?,?,?,?)",
                (uid, b["book_id"], b.get("position",""), b.get("label",""), b.get("created_at", now))
            )
            imported["bookmarks"] += 1
        except Exception:
            pass
    for n in (data.get("notes") or []):
        try:
            conn.execute(
                "INSERT INTO notes(user_id,book_id,position,text,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (uid, n["book_id"], n.get("position",""), n.get("text",""),
                 n.get("created_at", now), n.get("updated_at", now))
            )
            imported["notes"] += 1
        except Exception:
            pass
    for r in (data.get("ratings") or []):
        try:
            conn.execute(
                "INSERT OR REPLACE INTO ratings(user_id,book_id,rating,review,created_at) VALUES(?,?,?,?,?)",
                (uid, r["book_id"], r.get("rating", 3), r.get("review",""), r.get("created_at", now))
            )
            imported["ratings"] += 1
        except Exception:
            pass
    conn.commit()
    return jsonify({"ok": True, "imported": imported})


# ── Upload API ─────────────────────────────────────────────────────────────────

@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "no file"}), 400
    f = request.files["file"]
    original_name = Path(f.filename or "unknown").name
    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if ext not in ALLOWED_UPLOAD_EXTS:
        return jsonify({"error": f"unsupported format: {ext}"}), 400

    data = f.read()
    sha256 = hashlib.sha256(data).hexdigest()

    conn = get_db()
    existing = conn.execute("SELECT id FROM files WHERE sha1=?", (sha256,)).fetchone()
    if existing:
        return jsonify({"status": "duplicate", "book_id": existing["id"]})

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._- ")
    safe_name = sha256[:8] + "_" + "".join(
        c if c in safe_chars else "_" for c in original_name
    )
    dest = UPLOAD_DIR / safe_name
    dest.write_bytes(data)

    now = time.time()
    # rel_path relative to ROOT so scan/serve work uniformly
    try:
        rel_path = str(dest.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        rel_path = str(dest.resolve())
    title = original_name.rsplit(".", 1)[0] if "." in original_name else original_name

    conn.execute(
        "INSERT INTO files(rel_path,name,ext,size,mtime,fingerprint,sha1,kind,scanned_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (rel_path, original_name, ext, len(data), now, sha256[:16], sha256, "book", now)
    )
    file_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    conn.execute(
        "INSERT INTO metadata(file_id,title,source,confidence,extracted_at,cluster_role) VALUES(?,?,?,?,?,?)",
        (file_id, title, "upload", 0.5, now, "primary")
    )
    conn.commit()

    return jsonify({"status": "ok", "book_id": file_id})


# ── HTML Templates ─────────────────────────────────────────────────────────────

HOME_HTML = """<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>书库</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif;
         margin: 0; background: #f7f6f3; color: #222; }
  header { padding: .75rem 1.5rem; background: #fff; border-bottom: 1px solid #e5e3dd;
           display: flex; gap: .75rem; align-items: center; position: sticky; top: 0; z-index: 10; flex-wrap: wrap; }
  header h1 { margin: 0; font-size: 1.1rem; font-weight: 600; flex-shrink: 0; }
  header input, header select { padding: .4rem .6rem; border: 1px solid #d0cdc4;
           border-radius: 6px; background: #fff; font-size: .9rem; }
  header input[type="search"] { width: 200px; }
  .hdr-right { margin-left: auto; display: flex; gap: .5rem; align-items: center; }
  .icon-btn { padding: .4rem .7rem; border: 1px solid #d0cdc4; border-radius: 6px;
              background: #fff; cursor: pointer; font-size: .9rem; line-height: 1; }
  .icon-btn:hover { background: #f0ede8; }
  main { padding: 1.5rem; }
  .section-label { color: #a09070; font-size: .8rem; margin-bottom: .6rem; font-weight: 500; }
  .continue-row { display: flex; gap: .9rem; overflow-x: auto; padding-bottom: .8rem; margin-bottom: 1.5rem; }
  .continue-row::-webkit-scrollbar { height: 4px; }
  .continue-row::-webkit-scrollbar-thumb { background: #d0cdc4; border-radius: 2px; }
  .continue-card { flex-shrink: 0; width: 120px; text-decoration: none; color: inherit; }
  .continue-card img { width: 120px; height: 168px; object-fit: cover; border-radius: 4px;
                       box-shadow: 0 1px 4px rgba(0,0,0,.1); display: block; background: #eee; }
  .prog-bar { background: #e8e6df; height: 4px; border-radius: 2px; margin: .35rem 0 .2rem; }
  .prog-fill { background: #2d6cdf; height: 100%; border-radius: 2px; max-width: 100%; }
  .continue-card .ct { font-size: .75rem; line-height: 1.3; overflow: hidden;
                       display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  .continue-card .cp { font-size: .68rem; color: #999; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
          gap: 1.2rem; }
  .card { background: #fff; border-radius: 8px; overflow: hidden; text-decoration: none; color: inherit;
          box-shadow: 0 1px 3px rgba(0,0,0,.06); transition: transform .15s; cursor: pointer; display: block; }
  .card:hover { transform: translateY(-2px); box-shadow: 0 4px 10px rgba(0,0,0,.08); }
  .card .cov { aspect-ratio: 5/7; background: #eee; width: 100%; object-fit: cover; display: block; }
  .card .meta { padding: .5rem .7rem .7rem; }
  .card .t { font-size: .85rem; font-weight: 500; line-height: 1.3;
             display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .card .a { font-size: .75rem; color: #777; margin-top: .25rem;
             white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .card .ext { font-size: .65rem; color: #999; text-transform: uppercase; margin-top: .2rem; }
  footer { padding: 2rem; text-align: center; color: #888; font-size: .85rem; }
  .pager { display: flex; gap: .5rem; justify-content: center; padding: 1rem; }
  .pager button { padding: .4rem .8rem; border: 1px solid #d0cdc4; background: #fff;
                  border-radius: 4px; cursor: pointer; }
  .pager button:disabled { opacity: .4; cursor: not-allowed; }
  .empty { text-align: center; color: #888; padding: 4rem; }
  /* User sidebar */
  .overlay { position: fixed; inset: 0; background: rgba(0,0,0,.35); z-index: 100; }
  .sidebar { position: fixed; top: 0; right: 0; bottom: 0; width: 300px; background: #fff;
             z-index: 101; padding: 1.5rem; overflow-y: auto;
             box-shadow: -3px 0 12px rgba(0,0,0,.12); }
  .sidebar h2 { margin: 0 0 1.2rem; font-size: 1rem; }
  .sidebar label { display: block; font-size: .8rem; color: #666; margin-bottom: .25rem; }
  .sidebar input[type=text] { width: 100%; box-sizing: border-box; padding: .4rem .6rem;
                              border: 1px solid #d0cdc4; border-radius: 6px; font-size: .9rem; }
  .sidebar hr { border: none; border-top: 1px solid #eee; margin: 1rem 0; }
  .sidebar .sm-btn { display: inline-block; padding: .4rem .9rem; border-radius: 6px;
                     background: #2d6cdf; color: #fff; border: 0; cursor: pointer; font-size: .85rem; }
  .sidebar .sm-btn.sec { background: #eee; color: #333; }
  .sidebar .uid { font-family: monospace; font-size: .75rem; color: #888; word-break: break-all;
                  background: #f5f5f5; padding: .3rem .5rem; border-radius: 4px; cursor: pointer; }
  /* Upload modal */
  .modal-wrap { position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 200;
                display: flex; align-items: center; justify-content: center; }
  .modal-box { background: #fff; border-radius: 10px; padding: 2rem; width: min(90vw, 480px); }
  .modal-box h2 { margin: 0 0 1rem; font-size: 1rem; }
  .drop-zone { border: 2px dashed #d0cdc4; border-radius: 8px; padding: 2.5rem 1rem;
               text-align: center; color: #888; cursor: pointer; transition: .15s; }
  .drop-zone.dragover { border-color: #2d6cdf; background: #f0f5ff; color: #2d6cdf; }
  .progress-wrap { margin-top: 1rem; display: none; }
  .upload-bar { background: #e8e6df; height: 6px; border-radius: 3px; }
  .upload-fill { background: #2d6cdf; height: 100%; border-radius: 3px; width: 0; transition: width .3s; }
  .upload-status { font-size: .85rem; color: #555; margin-top: .5rem; }
  @media(max-width:640px){
    header { padding:.6rem .8rem; gap:.5rem; }
    header h1 { font-size:.95rem; }
    header input[type="search"] { width:100%; flex:1 1 140px; }
    header select { font-size:.82rem; padding:.32rem .4rem; max-width:110px; }
    .hdr-right { margin-left:0; flex:0 0 auto; }
    #count { display:none; }
    main { padding:.9rem; }
    .grid { grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap:.8rem; }
    .sidebar { width:min(90vw, 300px); }
  }
  @media(max-width:420px){
    #subject, #decade, #ext { display:none; }
  }
</style></head>
<body>
<header>
  <h1>📚 书库</h1>
  <input type="search" id="q" placeholder="搜索书名或作者…">
  <select id="category"><option value="">所有分类</option></select>
  <select id="category2" disabled><option value="">— 二级分类 —</option></select>
  <select id="subject" disabled><option value="">— 跨界相关 —</option></select>
  <select id="author"><option value="">所有作者</option></select>
  <select id="decade"><option value="">所有年代</option></select>
  <select id="ext"><option value="">所有格式</option></select>
  <select id="sort">
    <option value="title">按书名</option>
    <option value="pinyin">按书名 A-Z(拼音)</option>
    <option value="author">按作者</option>
    <option value="pub_year_desc">出版年代(新→旧)</option>
    <option value="pub_year_asc">出版年代(旧→新)</option>
    <option value="id">按入库</option>
    <option value="confidence">按置信度</option>
  </select>
  <div class="hdr-right">
    <span id="count" style="color:#777;font-size:.85rem;"></span>
    <button class="icon-btn" onclick="goRandom()" title="随机推荐一本书">🎲</button>
    <button class="icon-btn" onclick="showUpload()" title="上传书籍">⬆ 上传</button>
    <a class="icon-btn" href="/shelf" title="我的书架" id="btn-shelf" style="text-decoration:none;">🗂️</a>
    <a class="icon-btn" href="/admin" title="管理后台" style="text-decoration:none;">⚙️</a>
    <button class="icon-btn" id="btn-user" onclick="toggleSidebar()" title="我的账号">👤</button>
  </div>
</header>

<!-- User sidebar -->
<div id="sidebar-wrap" style="display:none;">
  <div class="overlay" onclick="toggleSidebar()"></div>
  <div class="sidebar">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.2rem;">
      <h2 style="margin:0;">📖 我的账号</h2>
      <button onclick="toggleSidebar()" style="background:none;border:0;cursor:pointer;font-size:1.3rem;color:#aaa;line-height:1;">×</button>
    </div>

    <!-- 显示名 -->
    <label>显示名</label>
    <div style="display:flex;gap:.5rem;margin-bottom:.8rem;">
      <input type="text" id="display-name" placeholder="未设置" maxlength="50" style="flex:1;">
      <button class="sm-btn" onclick="saveName()">保存</button>
    </div>

    <!-- 设备 ID -->
    <label>设备 ID（点击复制）</label>
    <div class="uid" id="uid-display" onclick="copyUid()">—</div>

    <!-- 最近阅读 -->
    <div style="margin-top:1rem;">
      <label>最近阅读</label>
      <div id="sidebar-history" style="font-size:.82rem;color:#888;margin-top:.3rem;">加载中…</div>
    </div>

    <hr>

    <!-- 合并账号 -->
    <label>合并另一台设备的账号</label>
    <div style="font-size:.77rem;color:#aaa;margin:.2rem 0 .5rem;">
      输入另一个设备 ID，先预览再确认合并
    </div>
    <div style="display:flex;gap:.5rem;">
      <input type="text" id="merge-id" placeholder="粘贴另一个设备 ID" style="flex:1;font-size:.82rem;">
      <button class="sm-btn sec" onclick="previewMerge()">预览</button>
    </div>
    <!-- 预览区 -->
    <div id="merge-preview" style="display:none;margin-top:.75rem;background:#f7f6f3;border-radius:6px;padding:.8rem;border:1px solid #e8e6df;">
      <div id="merge-preview-content"></div>
      <div style="margin-top:.7rem;display:flex;gap:.5rem;">
        <button class="sm-btn" onclick="confirmMerge()">确认合并到当前账号</button>
        <button class="sm-btn sec" onclick="cancelMerge()">取消</button>
      </div>
    </div>

    <hr>

    <!-- 导出/导入 -->
    <div style="display:flex;gap:.5rem;flex-wrap:wrap;">
      <button class="sm-btn sec" onclick="exportData()">导出数据</button>
      <label class="sm-btn sec" style="cursor:pointer;">
        导入数据 <input type="file" accept=".json" style="display:none;" onchange="importData(this)">
      </label>
    </div>
    <div id="sidebar-msg" style="margin-top:.8rem;font-size:.82rem;color:#555;min-height:1.2em;"></div>
  </div>
</div>

<!-- Upload modal -->
<div id="upload-modal" style="display:none;">
  <div class="modal-wrap">
    <div class="modal-box">
      <h2>⬆ 上传书籍</h2>
      <div class="drop-zone" id="drop-zone"
           ondragover="event.preventDefault();this.classList.add('dragover')"
           ondragleave="this.classList.remove('dragover')"
           ondrop="handleDrop(event)">
        <div>拖拽文件到此处，或</div>
        <label style="color:#2d6cdf;cursor:pointer;margin-top:.5rem;display:inline-block;">
          选择文件
          <input type="file" id="file-input" accept=".epub,.pdf,.txt,.docx,.doc,.mobi,.azw3,.azw"
                 style="display:none;" onchange="uploadFile(this.files[0])">
        </label>
        <div style="font-size:.78rem;color:#aaa;margin-top:.5rem;">
          支持 EPUB / PDF / TXT / DOCX / MOBI / AZW3，最大 200 MB
        </div>
      </div>
      <div class="progress-wrap" id="upload-progress">
        <div class="upload-bar"><div class="upload-fill" id="upload-fill"></div></div>
        <div class="upload-status" id="upload-status">准备上传…</div>
      </div>
      <div style="margin-top:1rem;text-align:right;">
        <button class="icon-btn" onclick="closeUpload()">关闭</button>
      </div>
    </div>
  </div>
</div>

<main>
  <div id="continue-section" style="display:none;">
    <div class="section-label">继续阅读</div>
    <div class="continue-row" id="continue-row"></div>
  </div>
  <div id="featured-hint" style="padding:.2rem 0 .6rem; color:#a09070; font-size:.8rem;">今日精选 · 每日更新</div>
  <div class="grid" id="grid"></div>
  <div class="pager">
    <button id="prev">上一页</button>
    <span id="pageinfo" style="padding:.5rem;"></span>
    <button id="next">下一页</button>
  </div>
</main>
<script>
let page = 1, perPage = 40, total = 0;
let featuredMode = true;
let featuredSeed = null;  // null = 今日日期种子
let UID = null;

const CATEGORY_LABEL = {
  tech: '科技工程', business: '商业管理', humanities: '人文社科',
  literature: '文学艺术', practical: '生活实用', education: '教育学习',
  reference: '工具书', other: '其他',
};
let CATEGORY_TREE = [];

// ── User init ────────────────────────────────────────────────────────────────
async function initUser() {
  UID = localStorage.getItem('books_uid');
  if (!UID) {
    try {
      const r = await fetch('/api/user/init', {
        method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}'
      });
      const d = await r.json();
      UID = d.id;
      localStorage.setItem('books_uid', UID);
    } catch(e) { return; }
  } else {
    fetch('/api/user/init', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({id: UID})
    }).catch(() => {});
  }
  loadUserInfo();
  loadContinueReading();
}

async function loadUserInfo() {
  if (!UID) return;
  try {
    const r = await fetch('/api/user/' + UID);
    if (!r.ok) return;
    const d = await r.json();
    document.getElementById('uid-display').textContent = UID;
    document.getElementById('display-name').value = d.name || '';
    document.getElementById('btn-user').textContent = d.name ? ('👤 ' + d.name.slice(0,8)) : '👤';
  } catch(e) {}
}

async function loadContinueReading() {
  if (!UID) return;
  try {
    const r = await fetch('/api/user/' + UID + '/history?limit=6');
    const d = await r.json();
    const allHist = d.history || [];
    const books = allHist.filter(b => (b.progress_pct || 0) < 0.95);
    // Update shelf badge
    if (allHist.length) {
      const shelf = document.getElementById('btn-shelf');
      if (shelf) shelf.title = '我的书架（' + allHist.length + ' 本）';
    }
    if (!books.length) return;
    document.getElementById('continue-section').style.display = 'block';
    const row = document.getElementById('continue-row');
    row.innerHTML = '';
    for (const b of books) {
      const pct = Math.round((b.progress_pct || 0) * 100);
      const a = document.createElement('a');
      a.className = 'continue-card';
      a.href = '/book/' + b.book_id;
      a.innerHTML = '<img src="/cover/' + b.book_id + '" loading="lazy">' +
        '<div class="prog-bar"><div class="prog-fill" style="width:' + pct + '%"></div></div>' +
        '<div class="ct">' + escapeHtml(b.title || '无题') + '</div>' +
        '<div class="cp">' + pct + '%</div>';
      row.appendChild(a);
    }
  } catch(e) {}
}

// ── User sidebar ─────────────────────────────────────────────────────────────
function toggleSidebar() {
  const el = document.getElementById('sidebar-wrap');
  const opening = el.style.display === 'none';
  el.style.display = opening ? 'block' : 'none';
  if (opening) loadSidebarHistory();
}
function copyUid() {
  if (UID) navigator.clipboard.writeText(UID).then(() => {
    setSidebarMsg('已复制 ID');
  });
}
function setSidebarMsg(msg) {
  const el = document.getElementById('sidebar-msg');
  el.textContent = msg;
  setTimeout(() => el.textContent = '', 3000);
}
async function saveName() {
  if (!UID) return;
  const name = document.getElementById('display-name').value.trim();
  await fetch('/api/user/' + UID + '/name', {
    method: 'PUT', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name})
  });
  document.getElementById('btn-user').textContent = name ? ('👤 ' + name.slice(0,8)) : '👤';
  setSidebarMsg('显示名已保存');
}

// 当前用户最近阅读列表
async function loadSidebarHistory() {
  if (!UID) return;
  const el = document.getElementById('sidebar-history');
  try {
    const r = await fetch('/api/user/' + UID + '/history?limit=8');
    const d = await r.json();
    const books = d.history || [];
    if (!books.length) { el.textContent = '暂无阅读记录'; return; }
    el.innerHTML = books.map(b => {
      const pct = Math.round((b.progress_pct || 0) * 100);
      return '<div style="padding:.3rem 0;border-bottom:1px solid #eee;display:flex;justify-content:space-between;align-items:center;gap:.5rem;">' +
        '<a href="/book/' + b.book_id + '" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;color:#222;text-decoration:none;font-size:.82rem;">' +
        escapeHtml(b.title || '无题') + '</a>' +
        '<span style="color:#aaa;font-size:.75rem;flex-shrink:0;">' + pct + '%</span>' +
        '</div>';
    }).join('');
  } catch(e) { el.textContent = '加载失败'; }
}

// 预览另一个账号（合并前确认）
async function previewMerge() {
  const otherId = document.getElementById('merge-id').value.trim();
  if (!otherId) { setSidebarMsg('请先输入另一个设备 ID'); return; }
  if (otherId === UID) { setSidebarMsg('不能合并自己'); return; }
  const previewEl = document.getElementById('merge-preview');
  const contentEl = document.getElementById('merge-preview-content');
  contentEl.innerHTML = '<span style="color:#aaa;font-size:.82rem;">加载中…</span>';
  previewEl.style.display = 'block';
  try {
    const [userR, histR] = await Promise.all([
      fetch('/api/user/' + otherId),
      fetch('/api/user/' + otherId + '/history?limit=6')
    ]);
    if (!userR.ok) {
      contentEl.innerHTML = '<span style="color:#c44;">找不到该账号，请检查 ID 是否正确</span>';
      return;
    }
    const user = await userR.json();
    const hist = await histR.json();
    const books = hist.history || [];
    let html = '<div style="font-size:.85rem;font-weight:600;margin-bottom:.3rem;">' +
      (user.name ? escapeHtml(user.name) : '匿名账号') + '</div>';
    html += '<div style="font-size:.75rem;color:#aaa;margin-bottom:.5rem;">阅读了 ' + books.length + ' 本书</div>';
    if (books.length) {
      html += books.map(b => {
        const pct = Math.round((b.progress_pct || 0) * 100);
        return '<div style="font-size:.8rem;padding:.2rem 0;border-bottom:1px solid #eee;display:flex;justify-content:space-between;">' +
          '<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;">' + escapeHtml(b.title || '无题') + '</span>' +
          '<span style="color:#aaa;margin-left:.5rem;flex-shrink:0;">' + pct + '%</span>' +
          '</div>';
      }).join('');
    } else {
      html += '<div style="font-size:.8rem;color:#aaa;">暂无阅读记录</div>';
    }
    contentEl.innerHTML = html;
  } catch(e) {
    contentEl.innerHTML = '<span style="color:#c44;">加载失败，请检查网络</span>';
  }
}
async function confirmMerge() {
  if (!UID) return;
  const otherId = document.getElementById('merge-id').value.trim();
  if (!otherId) return;
  const r = await fetch('/api/user/' + UID + '/merge', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({other_id: otherId})
  });
  const d = await r.json();
  if (d.ok) {
    setSidebarMsg('✓ 合并成功，阅读记录已合并');
    document.getElementById('merge-id').value = '';
    cancelMerge();
    loadSidebarHistory();
    loadContinueReading();
  } else {
    setSidebarMsg(d.error || '合并失败');
  }
}
function cancelMerge() {
  document.getElementById('merge-preview').style.display = 'none';
  document.getElementById('merge-preview-content').innerHTML = '';
}

async function exportData() {
  if (!UID) return;
  window.open('/api/user/' + UID + '/export');
}
async function importData(input) {
  if (!UID || !input.files[0]) return;
  const text = await input.files[0].text();
  let data;
  try { data = JSON.parse(text); } catch { setSidebarMsg('文件格式错误'); return; }
  const r = await fetch('/api/user/' + UID + '/import', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify(data)
  });
  const d = await r.json();
  setSidebarMsg(d.ok ? '导入成功：历史 ' + d.imported.history + ' 条' : '导入失败');
}

// ── Upload ────────────────────────────────────────────────────────────────────
function showUpload() { document.getElementById('upload-modal').style.display = 'block'; }
function closeUpload() {
  document.getElementById('upload-modal').style.display = 'none';
  document.getElementById('upload-progress').style.display = 'none';
  document.getElementById('upload-fill').style.width = '0';
  document.getElementById('upload-status').textContent = '准备上传…';
  document.getElementById('drop-zone').classList.remove('dragover');
}
function handleDrop(e) {
  e.preventDefault();
  document.getElementById('drop-zone').classList.remove('dragover');
  const file = e.dataTransfer.files[0];
  if (file) uploadFile(file);
}
async function uploadFile(file) {
  if (!file) return;
  const prog = document.getElementById('upload-progress');
  const fill = document.getElementById('upload-fill');
  const status = document.getElementById('upload-status');
  prog.style.display = 'block';
  fill.style.width = '10%';
  status.textContent = '上传中：' + file.name;

  const fd = new FormData();
  fd.append('file', file);

  try {
    fill.style.width = '40%';
    const r = await fetch('/api/upload', {method: 'POST', body: fd});
    fill.style.width = '100%';
    const d = await r.json();
    if (d.status === 'ok') {
      status.textContent = '上传成功！' + (d.book_id ? '' : '');
      if (d.book_id) {
        setTimeout(() => { closeUpload(); window.location.href = '/book/' + d.book_id; }, 800);
      }
    } else if (d.status === 'duplicate') {
      status.textContent = '该书已存在于书库';
      if (d.book_id) setTimeout(() => { closeUpload(); window.location.href = '/book/' + d.book_id; }, 1000);
    } else {
      status.textContent = '上传失败：' + (d.error || '未知错误');
    }
  } catch(e) {
    status.textContent = '上传失败：网络错误';
  }
}

// ── Random book ──────────────────────────────────────────────────────────────
async function goRandom() {
  try {
    const r = await fetch('/api/random');
    const d = await r.json();
    if (d.id) window.location.href = '/book/' + d.id;
  } catch(e) {}
}

// ── Facets & browse ───────────────────────────────────────────────────────────
async function loadFacets() {
  const r = await fetch('/api/facets');
  const d = await r.json();
  const sel = document.getElementById('ext');
  for (const e of d.exts) {
    const o = document.createElement('option');
    o.value = e; o.textContent = e.toUpperCase(); sel.appendChild(o);
  }
  CATEGORY_TREE = d.categories || [];
  const csel = document.getElementById('category');
  for (const c of CATEGORY_TREE) {
    const o = document.createElement('option');
    o.value = c.key;
    o.textContent = (CATEGORY_LABEL[c.key] || c.key) + ' (' + c.n + ')';
    csel.appendChild(o);
  }
  const asel = document.getElementById('author');
  for (const a of (d.authors || [])) {
    const o = document.createElement('option');
    o.value = a; o.textContent = a; asel.appendChild(o);
  }
  const dsel = document.getElementById('decade');
  for (const dec of (d.decades || [])) {
    const o = document.createElement('option');
    o.value = dec.key; o.textContent = dec.key + 's (' + dec.n + ')';
    dsel.appendChild(o);
  }
}

function updateCategory2(selectedL1) {
  const sel = document.getElementById('category2');
  sel.innerHTML = '<option value="">— 二级分类 —</option>';
  document.getElementById('subject').innerHTML = '<option value="">— 跨界相关 —</option>';
  document.getElementById('subject').disabled = true;
  if (!selectedL1) { sel.disabled = true; return; }
  const node = CATEGORY_TREE.find(c => c.key === selectedL1);
  if (!node || !node.subs.length) { sel.disabled = true; return; }
  sel.disabled = false;
  for (const s of node.subs) {
    const o = document.createElement('option');
    o.value = s.key; o.textContent = s.key + ' (' + s.n + ')';
    sel.appendChild(o);
  }
}
function updateSubject(selectedL1, selectedL2) {
  const sel = document.getElementById('subject');
  sel.innerHTML = '<option value="">— 跨界相关 —</option>';
  if (!selectedL1 || !selectedL2) { sel.disabled = true; return; }
  const c1 = CATEGORY_TREE.find(c => c.key === selectedL1);
  const c2 = c1 && c1.subs.find(s => s.key === selectedL2);
  if (!c2 || !c2.subjects || !c2.subjects.length) { sel.disabled = true; return; }
  sel.disabled = false;
  for (const sj of c2.subjects) {
    const o = document.createElement('option');
    o.value = sj.key; o.textContent = sj.key + ' (' + sj.n + ')';
    sel.appendChild(o);
  }
}

function enterBrowseMode() {
  if (featuredMode) {
    featuredMode = false;
    document.getElementById('featured-hint').style.display = 'none';
  }
}

async function load() {
  let d;
  if (featuredMode) {
    const url = featuredSeed ? '/api/featured?seed=' + encodeURIComponent(featuredSeed) : '/api/featured';
    const r = await fetch(url);
    d = await r.json();
    total = d.total;
    const label = featuredSeed ? '换一批精选 ' + total + ' 本' : '今日精选 ' + total + ' 本';
    document.getElementById('count').textContent = label;
    document.getElementById('pageinfo').textContent = '';
    document.getElementById('prev').disabled = true;
    document.getElementById('next').disabled = false;
    document.getElementById('next').textContent = '换一批 →';
  } else {
    document.getElementById('next').textContent = '下一页';
    const params = new URLSearchParams({
      page, per_page: perPage,
      q: document.getElementById('q').value.trim(),
      category: document.getElementById('category').value,
      category2: document.getElementById('category2').value,
      subject: document.getElementById('subject').value,
      author: document.getElementById('author').value,
      decade: document.getElementById('decade').value,
      ext: document.getElementById('ext').value,
      sort: document.getElementById('sort').value,
    });
    const r = await fetch('/api/books?' + params);
    d = await r.json();
    total = d.total;
    document.getElementById('count').textContent = '共 ' + total + ' 本';
    document.getElementById('pageinfo').textContent =
      '第 ' + page + ' / ' + Math.max(1, Math.ceil(total / perPage)) + ' 页';
    document.getElementById('prev').disabled = page <= 1;
    document.getElementById('next').disabled = page * perPage >= total;
  }
  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  if (d.books.length === 0) {
    grid.innerHTML = '<div class="empty">还没有匹配的书。可能是 extract / lookup 阶段还没跑完。</div>';
    return;
  }
  for (const b of d.books) {
    const a = document.createElement('a');
    a.className = 'card';
    a.href = '/book/' + b.id;
    a.innerHTML =
      '<img class="cov" src="/cover/' + b.id + '" loading="lazy">' +
      '<div class="meta">' +
        '<div class="t">' + escapeHtml(b.title || '无题') + '</div>' +
        '<div class="a">' + escapeHtml(b.author || '佚名') + '</div>' +
        '<div class="ext">' + (b.ext || '').toUpperCase() + '</div>' +
      '</div>';
    grid.appendChild(a);
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

document.getElementById('q').addEventListener('input', debounce(() => { enterBrowseMode(); page=1; load(); }, 250));
document.getElementById('category').addEventListener('change', (e) => {
  updateCategory2(e.target.value); enterBrowseMode(); page=1; load();
});
document.getElementById('category2').addEventListener('change', (e) => {
  updateSubject(document.getElementById('category').value, e.target.value);
  enterBrowseMode(); page=1; load();
});
document.getElementById('subject').addEventListener('change', () => { enterBrowseMode(); page=1; load(); });
document.getElementById('author').addEventListener('change', () => { enterBrowseMode(); page=1; load(); });
document.getElementById('decade').addEventListener('change', () => { enterBrowseMode(); page=1; load(); });
document.getElementById('ext').addEventListener('change', () => { enterBrowseMode(); page=1; load(); });
document.getElementById('sort').addEventListener('change', () => { enterBrowseMode(); page=1; load(); });
document.getElementById('prev').addEventListener('click', () => { page=Math.max(1,page-1); load(); });
document.getElementById('next').addEventListener('click', () => {
  if (featuredMode) {
    // 换一批：用新随机种子重新拉精选
    featuredSeed = Date.now().toString(36) + Math.random().toString(36).slice(2);
    load();
  } else {
    page += 1; load();
  }
});

function debounce(fn, ms) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

loadFacets().then(load);
initUser();
</script></body></html>
"""


BOOK_HTML = """<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }}</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif;
         margin: 0; background: #f7f6f3; color: #222; }
  header { padding: .75rem 1.5rem; background: #fff; border-bottom: 1px solid #e5e3dd;
           display: flex; align-items: center; gap: 1rem; }
  header a { color: #555; text-decoration: none; }
  .wrap { max-width: 860px; margin: 2rem auto; padding: 0 1.5rem; }
  .top-grid { display: grid; grid-template-columns: 200px 1fr; gap: 2rem; }
  .cover { width: 200px; aspect-ratio: 5/7; object-fit: cover; border-radius: 4px;
           box-shadow: 0 2px 6px rgba(0,0,0,.1); background: #eee; }
  .meta h1 { margin: 0 0 .5rem; font-size: 1.4rem; }
  .meta .author { color: #555; margin-bottom: .75rem; }
  .meta dl { margin: .5rem 0; }
  .meta dt { color: #888; font-size: .8rem; margin-top: .5rem; }
  .meta dd { margin: 0; font-size: .95rem; }
  .meta .summary { margin-top: 1.5rem; line-height: 1.7; color: #333;
                   white-space: pre-wrap; word-break: break-word; font-size: .9rem; }
  .actions { margin-top: 1.2rem; display: flex; gap: .7rem; flex-wrap: wrap; }
  .btn { padding: .5rem 1rem; border-radius: 6px; text-decoration: none;
         background: #2d6cdf; color: #fff; font-size: .9rem; border: 0; cursor: pointer; }
  .btn.sec { background: #eee; color: #333; }
  .tag { display: inline-block; background: #eee9d8; color: #6b5a1e; padding: .15rem .55rem;
         border-radius: 12px; font-size: .75rem; margin: .15rem .15rem 0 0; }
  /* Progress */
  .prog-section { margin: 1.5rem 0; }
  .prog-bar { background: #e8e6df; height: 6px; border-radius: 3px; margin: .4rem 0; }
  .prog-fill { background: #2d6cdf; height: 100%; border-radius: 3px; }
  /* Rating */
  .rating-section { margin: 1.5rem 0; }
  .stars { display: flex; gap: .2rem; }
  .star { font-size: 1.5rem; cursor: pointer; color: #d0cdc4; transition: color .1s; user-select: none; }
  .star.on { color: #f4b942; }
  .star:hover, .star.hover { color: #f4b942; }
  /* Sections */
  .section { margin: 2rem 0; }
  .section h3 { font-size: .95rem; color: #555; margin: 0 0 .75rem; font-weight: 600;
                border-bottom: 1px solid #e5e3dd; padding-bottom: .4rem; }
  /* Related books */
  .related-row { display: flex; gap: .9rem; overflow-x: auto; padding-bottom: .5rem; }
  .related-row::-webkit-scrollbar { height: 4px; }
  .related-row::-webkit-scrollbar-thumb { background: #d0cdc4; border-radius: 2px; }
  .rel-card { flex-shrink: 0; width: 110px; text-decoration: none; color: inherit; }
  .rel-card img { width: 110px; height: 154px; object-fit: cover; border-radius: 4px;
                  box-shadow: 0 1px 3px rgba(0,0,0,.1); display: block; background: #eee; }
  .rel-card .rt { font-size: .72rem; margin-top: .3rem; line-height: 1.3; overflow: hidden;
                  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  /* Variants */
  .variant-list { list-style: none; padding: 0; margin: .5rem 0; }
  .variant-list li { padding: .4rem 0; border-bottom: 1px solid #eee; }
  /* Notes */
  .note-item { background: #fffdf5; border: 1px solid #f0e8c0; border-radius: 6px;
               padding: .7rem; margin: .4rem 0; }
  .note-item .nt { font-size: .88rem; line-height: 1.6; white-space: pre-wrap; }
  .note-item .na { font-size: .72rem; color: #aaa; margin-top: .3rem; }
  /* Bookmarks */
  .bm-item { display: flex; align-items: center; gap: .45rem;
             padding: .4rem 0; border-bottom: 1px solid #f0ede8; font-size: .85rem; }
  .bm-dot { width:10px; height:10px; border-radius:50%; flex-shrink:0; }
  .bm-del { background: none; border: 0; color: #aaa; cursor: pointer; font-size: 1rem; margin-left: auto; }
  /* Note input */
  .note-input { width: 100%; box-sizing: border-box; padding: .5rem .7rem; border: 1px solid #d0cdc4;
                border-radius: 6px; font-size: .9rem; resize: vertical; min-height: 80px;
                font-family: inherit; }
  @media(max-width:600px){
    .wrap { padding:0 .8rem; margin:1rem auto; }
    .top-grid { grid-template-columns:1fr; }
    .cover { width:50%; max-width:160px; }
    .meta h1 { font-size:1.1rem; }
    header { padding:.6rem 1rem; }
  }
</style></head>
<body>
<header>
  <a href="/">← 书库</a>
  <a href="/shelf" style="margin-left:auto;color:#555;text-decoration:none;font-size:.85rem;">🗂️ 我的书架</a>
</header>
<div class="wrap" id="root">加载中…</div>
<script>
const id = {{ id }};
let UID = localStorage.getItem('books_uid');

async function ensureUser() {
  if (!UID) {
    try {
      const r = await fetch('/api/user/init', {
        method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'
      });
      const d = await r.json();
      UID = d.id;
      localStorage.setItem('books_uid', UID);
    } catch(e) {}
  }
}

async function load() {
  await ensureUser();
  const r = await fetch('/api/book/' + id);
  if (!r.ok) { document.getElementById('root').innerHTML = '<p>未找到</p>'; return; }
  const b = await r.json();
  document.title = b.title || '无题';

  const tags = tryParse(b.tags);
  const subjects = tryParse(b.subjects);
  const ext = (b.ext || '').toLowerCase();
  const canRead = ['epub','pdf','txt','docx','doc','mobi','azw3','azw'].includes(ext);
  const CAT_LABEL = {tech:'科技工程',business:'商业管理',humanities:'人文社科',literature:'文学艺术',practical:'生活实用',education:'教育学习',reference:'工具书',other:'其他'};
  const catLine = b.category
    ? esc(CAT_LABEL[b.category] || b.category) + (b.category2 ? ' · ' + esc(b.category2) : '')
    : '';

  const root = document.getElementById('root');
  root.innerHTML = '<div class="top-grid">' +
    '<img class="cover" src="/cover/' + id + '">' +
    '<div class="meta">' +
      '<h1>' + esc(b.title || '无题') + '</h1>' +
      '<div class="author">' + esc(b.author || '佚名') + '</div>' +
      (catLine ? '<div style="margin:.3rem 0;color:#6b5a1e;font-size:.85rem;">' + catLine + '</div>' : '') +
      '<div>' + subjects.map(t => '<span class="tag">' + esc(t) + '</span>').join('') + '</div>' +
      '<div class="actions" id="actions">' +
        (canRead ? '<a class="btn" href="/read/' + id + '" id="read-btn">📖 在线阅读</a>' : '') +
        '<a class="btn sec" href="/file/' + id + '" download>⬇ 下载</a>' +
      '</div>' +
      '<div id="prog-section"></div>' +
      '<dl>' +
        (b.publisher ? '<dt>出版社</dt><dd>' + esc(b.publisher) + '</dd>' : '') +
        (b.pubdate ? '<dt>出版日期</dt><dd>' + esc(b.pubdate) + '</dd>' : '') +
        (b.isbn ? '<dt>ISBN</dt><dd>' + esc(b.isbn) + '</dd>' : '') +
        '<dt>格式</dt><dd>' + esc((b.ext||'').toUpperCase()) + ' · ' + fmtSize(b.size||0) + '</dd>' +
        '<dt>识别置信度</dt><dd>' + ((b.confidence||0)*100).toFixed(0) + '%</dd>' +
      '</dl>' +
      (b.variants && b.variants.length ? renderVariants(b.variants) : '') +
      (b.summary ? '<div class="summary">' + esc(b.summary) + '</div>' : '') +
    '</div>' +
  '</div>' +
  '<div id="rating-section"></div>' +
  '<div id="related-section"></div>' +
  '<div id="notes-section"></div>' +
  '<div id="bookmarks-section"></div>';

  // Load user data and related books in parallel
  loadUserData(id, canRead);
  loadRelated(id);
}

function tryParse(s) {
  if (!s) return [];
  try { return JSON.parse(s); } catch { return []; }
}
function renderVariants(vs) {
  return '<h3 style="margin-top:1.2rem;font-size:.9rem;color:#666;">其他版本（' + vs.length + '）</h3>' +
    '<ul class="variant-list">' +
    vs.map(v =>
      '<li><a href="/book/' + v.id + '" style="color:#2d6cdf;text-decoration:none;">' +
      (v.ext||'').toUpperCase() + '</a>' +
      (v.publisher ? ' · ' + esc(v.publisher) : '') +
      (v.pubdate ? ' · ' + esc(v.pubdate) : '') +
      ' <span style="color:#888;font-size:.8rem;">· ' + fmtSize(v.size||0) + '</span></li>'
    ).join('') + '</ul>';
}

async function loadUserData(bookId, canRead) {
  if (!UID) return;
  try {
    const r = await fetch('/api/user/' + UID + '/history/' + bookId);
    const h = await r.json();
    if (h && h.progress_pct > 0) {
      const pct = Math.round(h.progress_pct * 100);
      document.getElementById('prog-section').innerHTML =
        '<div style="margin-top:1rem;">' +
        '<div style="font-size:.8rem;color:#888;margin-bottom:.3rem;">阅读进度</div>' +
        '<div class="prog-bar"><div class="prog-fill" style="width:' + pct + '%"></div></div>' +
        '<div style="font-size:.78rem;color:#777;">' + pct + '%' +
        (h.last_read_at ? ' · 上次阅读：' + fmtDate(h.last_read_at) : '') + '</div>' +
        '</div>';
      if (canRead) {
        const btn = document.getElementById('read-btn');
        if (btn) btn.textContent = '📖 继续阅读 (' + pct + '%)';
      }
    }
  } catch(e) {}

  // Rating
  try {
    const rv = await fetch('/api/user/' + UID + '/history/' + bookId);
    // Just show the rating UI regardless
    renderRating(bookId, 0);
  } catch(e) { renderRating(bookId, 0); }

  // Notes
  loadNotes(bookId);
  loadBookmarks(bookId);
}

let currentRating = 0;
function renderRating(bookId, myRating) {
  currentRating = myRating;
  const el = document.getElementById('rating-section');
  el.innerHTML = '<div class="section">' +
    '<h3>我的评分</h3>' +
    '<div class="stars" id="stars">' +
    [1,2,3,4,5].map(i =>
      '<span class="star' + (i <= myRating ? ' on' : '') + '" data-v="' + i + '" ' +
      'onmouseenter="hoverStar(' + i + ')" onmouseleave="unhoverStar()" onclick="rateStar(' + bookId + ',' + i + ')">' +
      '★</span>'
    ).join('') +
    '</div></div>';
}

function hoverStar(v) {
  document.querySelectorAll('.star').forEach((s,i) => {
    s.classList.toggle('hover', i < v);
  });
}
function unhoverStar() {
  document.querySelectorAll('.star').forEach((s,i) => {
    s.classList.toggle('hover', false);
    s.classList.toggle('on', i < currentRating);
  });
}
async function rateStar(bookId, rating) {
  if (!UID) return;
  currentRating = rating;
  document.querySelectorAll('.star').forEach((s,i) => {
    s.classList.toggle('on', i < rating);
  });
  await fetch('/api/user/' + UID + '/rating', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({book_id: bookId, rating})
  });
}

async function loadNotes(bookId) {
  if (!UID) return;
  const el = document.getElementById('notes-section');
  try {
    const r = await fetch('/api/user/' + UID + '/notes/' + bookId);
    const d = await r.json();
    const notes = d.notes || [];
    el.innerHTML = '<div class="section">' +
      '<h3>我的笔记</h3>' +
      notes.map(n =>
        '<div class="note-item">' +
          '<div class="nt">' + esc(n.text) + '</div>' +
          '<div class="na">' + fmtDate(n.updated_at || n.created_at) +
          ' <button onclick="deleteNote(' + bookId + ',' + n.id + ')" style="background:none;border:0;color:#aaa;cursor:pointer;font-size:.8rem;">删除</button></div>' +
        '</div>'
      ).join('') +
      '<textarea class="note-input" id="note-input" placeholder="添加笔记…"></textarea>' +
      '<button class="btn sec" style="margin-top:.5rem;" onclick="addNote(' + bookId + ')">保存笔记</button>' +
    '</div>';
  } catch(e) {}
}

async function addNote(bookId) {
  if (!UID) return;
  const text = document.getElementById('note-input').value.trim();
  if (!text) return;
  await fetch('/api/user/' + UID + '/note', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({book_id: bookId, text})
  });
  loadNotes(bookId);
}

async function deleteNote(bookId, noteId) {
  if (!UID) return;
  await fetch('/api/user/' + UID + '/note/' + noteId, {method:'DELETE'});
  loadNotes(bookId);
}

const BM_COLORS = {red:'#e74c3c',orange:'#f39c12',green:'#27ae60',blue:'#3498db',purple:'#9b59b6'};
async function loadBookmarks(bookId) {
  if (!UID) return;
  const el = document.getElementById('bookmarks-section');
  try {
    const r = await fetch('/api/user/' + UID + '/bookmarks/' + bookId);
    const d = await r.json();
    const bms = d.bookmarks || [];
    if (!bms.length) { el.innerHTML = ''; return; }
    el.innerHTML = '<div class="section"><h3>书签（' + bms.length + '）</h3>' +
      bms.map(bm => {
        const col = BM_COLORS[bm.color] || BM_COLORS.orange;
        return '<div class="bm-item">' +
          '<span class="bm-dot" style="background:' + col + '"></span>' +
          '<span>' + esc(bm.label || bm.position || '书签') + '</span>' +
          '<button class="bm-del" onclick="deleteBm(' + bookId + ',' + bm.id + ')">×</button>' +
        '</div>';
      }).join('') +
    '</div>';
  } catch(e) {}
}

async function deleteBm(bookId, bmId) {
  if (!UID) return;
  await fetch('/api/user/' + UID + '/bookmark/' + bmId, {method:'DELETE'});
  loadBookmarks(bookId);
}

async function loadRelated(bookId) {
  const el = document.getElementById('related-section');
  try {
    const r = await fetch('/api/book/' + bookId + '/related');
    const d = await r.json();
    const books = d.related || [];
    if (!books.length) { el.innerHTML = ''; return; }
    el.innerHTML = '<div class="section"><h3>相关书籍</h3>' +
      '<div class="related-row">' +
      books.map(b =>
        '<a class="rel-card" href="/book/' + b.id + '">' +
          '<img src="/cover/' + b.id + '" loading="lazy">' +
          '<div class="rt">' + esc(b.title || '无题') + '</div>' +
        '</a>'
      ).join('') +
      '</div></div>';
  } catch(e) {}
}

function esc(s) {
  return String(s||'').replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function fmtSize(n) {
  const u=['B','KB','MB','GB']; let i=0;
  while(n>=1024&&i<u.length-1){n/=1024;i++;}
  return n.toFixed(1)+u[i];
}
function fmtDate(ts) {
  if (!ts) return '';
  return new Date(ts*1000).toLocaleDateString('zh-CN');
}

load();
</script></body></html>
"""


READER_EPUB_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>阅读</title>
<script src="https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/epubjs@0.3.93/dist/epub.min.js"></script>
<style>
  body { margin: 0; background: #2a2a2a; color: #ddd; height: 100vh;
         display: flex; flex-direction: column; font-family: -apple-system, sans-serif; }
  header { padding: .5rem 1rem; background: #1f1f1f; display: flex; gap: .8rem;
           align-items: center; border-bottom: 1px solid #333; flex-shrink: 0; }
  header a { color: #aaa; text-decoration: none; }
  #viewer { flex: 1; background: #fff; color: #222; overflow: hidden; }
  button { padding: .4rem .8rem; background: #444; color: #ddd; border: 0;
           border-radius: 4px; cursor: pointer; }
  .hdr-btn { padding: .4rem .8rem; background: #444; color: #ddd !important;
             border-radius: 4px; text-decoration: none !important; }
  #save-indicator { font-size: .72rem; color: #666; }
  /* Seek bar (inline in header) */
  #seek-inline { flex:1; display:flex; align-items:center; gap:.5rem; min-width:80px; }
  #seek-bar { flex:1; height:6px; -webkit-appearance:none; appearance:none; background:#555;
              border-radius:3px; outline:none; cursor:pointer; accent-color:#2d6cdf; }
  #seek-bar::-webkit-slider-thumb { -webkit-appearance:none; width:14px; height:14px;
    border-radius:50%; background:#2d6cdf; cursor:grab; }
  #seek-bar::-webkit-slider-runnable-track { border-radius:3px; }
  #loc { font-size:.78rem; color:#888; white-space:nowrap; flex-shrink:0; }
  /* Shared side panel */
  .np, .bp { position:fixed; right:0; top:0; bottom:0; width:290px; background:#fff; color:#222;
             border-left:2px solid #333; z-index:50; display:flex; flex-direction:column;
             box-shadow:-4px 0 20px rgba(0,0,0,.5); }
  .np-hd, .bp-hd { padding:.65rem 1rem; background:#1f1f1f; color:#ddd; display:flex;
                   justify-content:space-between; align-items:center; flex-shrink:0; font-size:.9rem; }
  .np-body, .bp-body { flex:1; overflow-y:auto; padding:.6rem; }
  .np-foot, .bp-foot { padding:.65rem; border-top:1px solid #e8e6df; flex-shrink:0; }
  .ni { background:#fffdf5; border:1px solid #f0e8c0; border-radius:5px;
        padding:.55rem; margin-bottom:.5rem; }
  .ni .nt { font-size:.82rem; line-height:1.55; white-space:pre-wrap; }
  .ni .nm { font-size:.7rem; color:#aaa; margin-top:.3rem; }
  .nt-area { width:100%; box-sizing:border-box; min-height:75px; padding:.45rem;
             border:1px solid #ccc; border-radius:5px; font-size:.85rem;
             resize:vertical; font-family:inherit; }
  .save-btn { margin-top:.4rem; padding:.35rem .8rem; background:#2d6cdf; color:#fff;
              border:0; border-radius:4px; cursor:pointer; font-size:.85rem; }
  /* Bookmark panel specifics */
  .cp-wrap { display:flex; gap:.4rem; margin-bottom:.5rem; align-items:center; }
  .cp-dot { width:22px; height:22px; border-radius:50%; cursor:pointer; display:inline-block;
            outline:2px solid transparent; outline-offset:2px; flex-shrink:0; }
  .bkm-in { width:100%; box-sizing:border-box; padding:.4rem; border:1px solid #ccc;
            border-radius:5px; font-size:.82rem; margin:.3rem 0; font-family:inherit; }
  .bkm-row { display:flex; align-items:center; gap:.45rem; padding:.4rem .2rem;
             border-bottom:1px solid #f0ede8; }
  .bk-dot { width:12px; height:12px; border-radius:50%; flex-shrink:0; }
  .bkm-info { flex:1; min-width:0; }
  .bkm-lbl { font-size:.82rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .bkm-pos { font-size:.7rem; color:#aaa; }
  .bkm-go { background:none; border:0; color:#2d6cdf; cursor:pointer; font-size:.78rem;
            padding:.1rem .3rem; flex-shrink:0; }
  .bkm-x { background:none; border:0; color:#bbb; cursor:pointer; font-size:.9rem;
           padding:.1rem .3rem; flex-shrink:0; }
  /* TOC panel (left side) */
  .tp { position:fixed; left:0; top:0; bottom:0; width:280px; background:#fff; color:#222;
        border-right:2px solid #333; z-index:50; display:flex; flex-direction:column;
        box-shadow:4px 0 20px rgba(0,0,0,.5); }
  .tp-hd { padding:.65rem 1rem; background:#1f1f1f; color:#ddd; display:flex;
           justify-content:space-between; align-items:center; flex-shrink:0; font-size:.9rem; }
  .tp-body { flex:1; overflow-y:auto; }
  .tc-item { padding:.45rem .7rem; cursor:pointer; font-size:.82rem;
             border-bottom:1px solid #f0ede8; line-height:1.4; }
  .tc-item:hover { background:#f5f3ee; }
  #btm-bar { display:none; position:fixed; bottom:0; left:0; right:0;
             background:#1c1c1c; border-top:1px solid #333; padding:.4rem .8rem;
             align-items:center; z-index:4; }
  header.hidden { display:none !important; }
  #btm-bar.hidden { display:none !important; }
  @media(max-width:540px){
    header { gap:.4rem; padding:.4rem .6rem; }
    button, .hdr-btn { padding:.3rem .5rem; font-size:.78rem; }
    header #seek-inline { display:none; }
    #btm-bar { display:flex; }
    #viewer { margin-bottom:46px; }
    #seek-bar { touch-action:none; }
    #seek-bar::-webkit-slider-thumb { width:22px; height:22px; }
  }
</style></head>
<body>
<header>
  <a href="/">🏠</a>
  <a href="/book/{{ id }}" class="hdr-btn">详情</a>
  <button onclick="toggleToc()">目录</button>
  <button id="prev">上一页</button>
  <button id="next">下一页</button>
  <button onclick="adjFont(-1)" title="缩小字体">A-</button>
  <button onclick="adjFont(1)" title="放大字体">A+</button>
  <div id="seek-inline">
    <input type="range" id="seek-bar" min="0" max="100" value="0">
    <span id="loc"></span>
  </div>
  <button onclick="toggleNotes()" title="笔记">📝</button>
  <button onclick="toggleBkm()" title="书签">🔖</button>
  <span id="save-indicator" style="font-size:.72rem;color:#666;"></span>
</header>
<div id="viewer"></div>
<div id="btm-bar"></div>
<!-- TOC panel -->
<div class="tp" id="tp" style="display:none;">
  <div class="tp-hd">☰ 目录
    <button onclick="toggleToc()" style="background:none;border:0;color:#aaa;cursor:pointer;font-size:1.2rem;line-height:1;">×</button>
  </div>
  <div class="tp-body" id="tp-body"><div style="color:#aaa;font-size:.82rem;padding:.6rem;">加载中…</div></div>
</div>
<!-- Notes panel -->
<div class="np" id="np" style="display:none;">
  <div class="np-hd">📝 笔记
    <button onclick="toggleNotes()" style="background:none;border:0;color:#aaa;cursor:pointer;font-size:1.2rem;line-height:1;">×</button>
  </div>
  <div class="np-body" id="np-body"><div style="color:#aaa;font-size:.82rem;padding:.3rem;">加载中…</div></div>
  <div class="np-foot">
    <textarea class="nt-area" id="nt-input" placeholder="摘录或笔记（自动记录当前位置）"></textarea>
    <button class="save-btn" onclick="saveNote()">保存笔记</button>
  </div>
</div>
<!-- Bookmark panel -->
<div class="bp" id="bp" style="display:none;">
  <div class="bp-hd">🔖 书签
    <button onclick="toggleBkm()" style="background:none;border:0;color:#aaa;cursor:pointer;font-size:1.2rem;line-height:1;">×</button>
  </div>
  <div class="bp-body">
    <div class="bp-foot" style="border-top:none;border-bottom:1px solid #f0ede8;margin-bottom:.4rem;">
      <div style="font-size:.75rem;color:#888;margin-bottom:.35rem;">选颜色</div>
      <div class="cp-wrap" id="cp-wrap">
        <span class="cp-dot" data-c="red"    style="background:#e74c3c;" onclick="selColor(this)"></span>
        <span class="cp-dot" data-c="orange" style="background:#f39c12;outline-color:#333;" onclick="selColor(this)"></span>
        <span class="cp-dot" data-c="green"  style="background:#27ae60;" onclick="selColor(this)"></span>
        <span class="cp-dot" data-c="blue"   style="background:#3498db;" onclick="selColor(this)"></span>
        <span class="cp-dot" data-c="purple" style="background:#9b59b6;" onclick="selColor(this)"></span>
      </div>
      <input class="bkm-in" id="bkm-in" placeholder="书签备注（可选，默认用位置）">
      <button class="save-btn" style="width:100%;" onclick="addBkm()">添加书签到当前位置</button>
    </div>
    <div id="bp-list"><div style="color:#aaa;font-size:.82rem;padding:.3rem;">加载中…</div></div>
  </div>
</div>
<script>
const BOOK_ID = {{ id }};
const UID = localStorage.getItem('books_uid');
let rendition, book;
let saveTimer = null;
let notesOpen = false;
let tocItems = [], tocOpen = false;
let totalLocs = 0;
const seekBar = document.getElementById('seek-bar');
const fontSizes = ['70%','80%','85%','90%','95%','100%','110%','120%'];
let fontSizeIdx = parseInt(localStorage.getItem('epub_font_idx') || '5');
function adjFont(d) {
  fontSizeIdx = Math.max(0, Math.min(fontSizes.length-1, fontSizeIdx+d));
  localStorage.setItem('epub_font_idx', fontSizeIdx);
  if (rendition) rendition.themes.fontSize(fontSizes[fontSizeIdx]);
}

async function init() {
  const resp = await fetch('/file/{{ id }}');
  if (!resp.ok) { document.getElementById('viewer').textContent = '文件加载失败'; return; }
  const buffer = await resp.arrayBuffer();
  book = ePub(buffer);
  rendition = book.renderTo('viewer', { width: '100%', height: '100%', flow: 'paginated', minSpreadWidth: 9999 });
  rendition.themes.fontSize(fontSizes[fontSizeIdx]);
  rendition.hooks.content.register(c => {
    const s = c.document.createElement('style');
    s.textContent = 'body{padding-top:1rem!important;padding-bottom:1rem!important;}';
    c.document.head.appendChild(s);
  });
  book.ready.then(() => book.locations.generate(1024).then(() => {
    totalLocs = book.locations.total();
    seekBar.max = totalLocs;
    const curLoc = rendition.currentLocation();
    if (curLoc && curLoc.start) {
      seekBar.value = curLoc.start.location || Math.round((curLoc.start.percentage||0) * totalLocs);
    }
  }));

  let startCfi = null;
  if (UID) {
    try {
      const r = await fetch('/api/user/' + UID + '/history/' + BOOK_ID);
      const h = await r.json();
      if (h && h.last_position && h.last_position.startsWith('epubcfi')) startCfi = h.last_position;
    } catch(e) {}
  }
  rendition.display(startCfi || undefined);

  rendition.on('relocated', loc => {
    const cfi = loc.start.cfi || '';
    const locEl = document.getElementById('loc');
    let bookPct = 0;
    if (totalLocs > 0 && loc.start.location) {
      bookPct = loc.start.location / totalLocs;
      locEl.textContent = loc.start.location + ' / ' + totalLocs + ' 页';
      seekBar.value = loc.start.location;
    } else {
      bookPct = loc.start.percentage || 0;
      locEl.textContent = bookPct > 0 ? Math.round(bookPct * 100) + '%' : '';
      seekBar.value = Math.round(bookPct * 100);
    }
    scheduleSave(cfi, bookPct);
  });

  book.loaded.navigation.then(nav => {
    const toc = nav.toc || [];
    if (toc.length > 0) {
      tocItems = flattenToc(toc);
    } else {
      tocItems = (book.spine.items || []).slice(0, 30).map((item, i) => ({
        label: '第 ' + (i + 1) + ' 章', href: item.href || '', depth: 0
      }));
    }
  });
}

function scheduleSave(cfi, pct) {
  if (!UID) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => saveProgress(cfi, pct), 5000);
}
async function saveProgress(cfi, pct) {
  if (!UID) return;
  try {
    await fetch('/api/user/' + UID + '/history', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({book_id:BOOK_ID, progress_pct:pct, last_position:cfi})
    });
    const ind = document.getElementById('save-indicator');
    ind.textContent = '已保存'; setTimeout(() => ind.textContent='', 2000);
  } catch(e) {}
}
function getCurrentPos() {
  if (!rendition) return '';
  try { const l = rendition.currentLocation(); return l&&l.start?l.start.cfi:''; } catch(e){return '';}
}

// TOC panel
function flattenToc(items, depth) {
  depth = depth || 0;
  const result = [];
  for (const item of (items || [])) {
    result.push({label:(item.label||'').trim(), href:item.href||'', depth});
    if (item.subitems && item.subitems.length) result.push(...flattenToc(item.subitems, depth+1));
  }
  return result;
}
function toggleToc() {
  tocOpen = !tocOpen;
  document.getElementById('tp').style.display = tocOpen ? 'flex' : 'none';
  if (tocOpen) loadToc();
}
function loadToc() {
  const el = document.getElementById('tp-body');
  if (!tocItems.length) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.6rem;">暂无目录</div>'; return; }
  el.innerHTML = tocItems.map((item, i) =>
    '<div class="tc-item" style="padding-left:'+(0.7+item.depth*1.1)+'rem" onclick="jumpChapter('+i+')">'+en(item.label||'章节')+'</div>'
  ).join('');
}
function jumpChapter(idx) {
  const item = tocItems[idx];
  if (item && rendition) rendition.display(item.href);
  toggleToc();
}

// Notes panel
function toggleNotes() {
  notesOpen = !notesOpen;
  document.getElementById('np').style.display = notesOpen ? 'flex' : 'none';
  if (notesOpen) loadNotes();
}
async function loadNotes() {
  const el = document.getElementById('np-body');
  if (!UID) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.3rem;">请先在首页激活账号</div>'; return; }
  try {
    const r = await fetch('/api/user/'+UID+'/notes/'+BOOK_ID);
    const d = await r.json();
    const notes = d.notes || [];
    if (!notes.length) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.3rem;">暂无笔记，在下方输入保存</div>'; return; }
    el.innerHTML = notes.map(n =>
      '<div class="ni"><div class="nt">'+en(n.text)+'</div>' +
      '<div class="nm">'+fd(n.updated_at||n.created_at)+
      ' <button onclick="delNote('+n.id+')" style="background:none;border:0;color:#bbb;cursor:pointer;font-size:.75rem;">删除</button></div></div>'
    ).join('');
  } catch(e) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.3rem;">加载失败</div>'; }
}
async function saveNote() {
  if (!UID) return;
  const text = document.getElementById('nt-input').value.trim();
  if (!text) return;
  await fetch('/api/user/'+UID+'/note', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({book_id:BOOK_ID, text, position:getCurrentPos()})
  });
  document.getElementById('nt-input').value='';
  loadNotes();
}
async function delNote(id) {
  if (!UID) return;
  await fetch('/api/user/'+UID+'/note/'+id, {method:'DELETE'});
  loadNotes();
}
function en(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function fd(ts){return ts?new Date(ts*1000).toLocaleDateString('zh-CN'):'';}

// ── Bookmarks ─────────────────────────────────────────────────────────────────
const CMAP = {red:'#e74c3c',orange:'#f39c12',green:'#27ae60',blue:'#3498db',purple:'#9b59b6'};
let bkmColor = 'orange', bkmPositions = [], bkmOpen = false;
function selColor(el) {
  bkmColor = el.dataset.c;
  document.querySelectorAll('.cp-dot').forEach(d => d.style.outlineColor = 'transparent');
  el.style.outlineColor = '#333';
}
function toggleBkm() {
  bkmOpen = !bkmOpen;
  document.getElementById('bp').style.display = bkmOpen ? 'flex' : 'none';
  if (bkmOpen) { if (notesOpen) toggleNotes(); loadBkm(); }
}
async function loadBkm() {
  const el = document.getElementById('bp-list');
  if (!UID) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.3rem;">请先在首页激活账号</div>'; return; }
  try {
    const r = await fetch('/api/user/'+UID+'/bookmarks/'+BOOK_ID);
    const d = await r.json();
    const bkms = d.bookmarks || [];
    bkmPositions = bkms.map(b => b.position||'');
    if (!bkms.length) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.3rem;">暂无书签，在上方添加</div>'; return; }
    el.innerHTML = bkms.map((b,i) => {
      const col = CMAP[b.color]||CMAP.orange;
      const isEpub = (b.position||'').startsWith('epubcfi');
      const pos = isEpub ? '' : (b.position||'');
      return '<div class="bkm-row">' +
        '<span class="bk-dot" style="background:'+col+'"></span>' +
        '<div class="bkm-info">' +
          '<div class="bkm-lbl">'+en(b.label||'书签')+'</div>' +
          (pos?'<div class="bkm-pos">'+en(pos)+'</div>':'') +
        '</div>' +
        '<button class="bkm-go" onclick="jumpBkm('+i+')">跳转</button>' +
        '<button class="bkm-x" onclick="delBkm('+b.id+')">×</button>' +
      '</div>';
    }).join('');
  } catch(e) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.3rem;">加载失败</div>'; }
}
function getCurrentBkmPos() {
  if (!rendition) return '';
  try { const l=rendition.currentLocation(); return l&&l.start?l.start.cfi:''; } catch(e){return '';}
}
function getCurrentBkmLabel() {
  if (!rendition) return '';
  try { const l=rendition.currentLocation(); return l&&l.start&&l.start.location?'位置 '+l.start.location:''; } catch(e){return '';}
}
async function addBkm() {
  if (!UID) return;
  let label = document.getElementById('bkm-in').value.trim();
  const position = getCurrentBkmPos();
  if (!label) label = getCurrentBkmLabel();
  await fetch('/api/user/'+UID+'/bookmark', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({book_id:BOOK_ID, position, label, color:bkmColor})
  });
  document.getElementById('bkm-in').value='';
  loadBkm();
}
async function delBkm(id) {
  if (!UID) return;
  await fetch('/api/user/'+UID+'/bookmark/'+id, {method:'DELETE'});
  loadBkm();
}
function jumpBkm(idx) {
  const pos = bkmPositions[idx];
  if (pos && rendition) rendition.display(pos);
}

window.addEventListener('beforeunload', () => clearTimeout(saveTimer));
seekBar.addEventListener('change', () => {
  if (!book || !rendition) return;
  const pct = totalLocs > 0 ? seekBar.value / seekBar.max : seekBar.value / 100;
  try { const cfi = book.locations.cfiFromPercentage(pct); if (cfi) rendition.display(cfi); } catch(e) {}
});
if (window.innerWidth <= 540) {
  const btm = document.getElementById('btm-bar');
  const si = document.getElementById('seek-inline');
  if (btm && si) btm.appendChild(si);
}
if ('ontouchstart' in window) {
  const hd = document.querySelector('header');
  const ov = document.createElement('div');
  const bh = window.innerWidth <= 540 ? 46 : 0;
  ov.style.cssText = 'position:fixed;left:0;right:0;top:0px;bottom:' + bh + 'px;z-index:2;-webkit-tap-highlight-color:transparent;';
  document.body.appendChild(ov);
  let hdrTimer = null;
  function showHdr() {
    if (!hd) return;
    hd.classList.remove('hidden');
    ov.style.top = hd.offsetHeight + 'px';
    clearTimeout(hdrTimer);
    hdrTimer = setTimeout(hideHdr, 3000);
  }
  function hideHdr() {
    if (!hd) return;
    hd.classList.add('hidden');
    ov.style.top = '0px';
  }
  hdrTimer = setTimeout(hideHdr, 2000);
  let tx = 0, ty = 0, moved = false;
  ov.addEventListener('touchstart', e => { tx = e.touches[0].clientX; ty = e.touches[0].clientY; moved = false; }, {passive:true});
  ov.addEventListener('touchmove', e => { if (Math.abs(e.touches[0].clientX-tx)+Math.abs(e.touches[0].clientY-ty) > 8) moved = true; }, {passive:true});
  ov.addEventListener('touchend', e => {
    const dx = e.changedTouches[0].clientX - tx, dy = e.changedTouches[0].clientY - ty;
    const adx = Math.abs(dx), ady = Math.abs(dy);
    if (adx > 40 && adx > ady) { if (dx < 0) rendition && rendition.next(); else rendition && rendition.prev(); }
    else if (ady > 40 && ady > adx) { if (dy < 0) rendition && rendition.next(); else rendition && rendition.prev(); }
    else if (!moved) {
      if (hd && hd.classList.contains('hidden')) showHdr();
      else { if (e.changedTouches[0].clientX > window.innerWidth/2) rendition && rendition.next(); else rendition && rendition.prev(); }
    }
  }, {passive:true});
}
init();
document.getElementById('prev').onclick = () => rendition && rendition.prev();
document.getElementById('next').onclick = () => rendition && rendition.next();
document.addEventListener('keydown', e => {
  if (e.key === 'ArrowRight' && rendition) rendition.next();
  if (e.key === 'ArrowLeft' && rendition) rendition.prev();
});
</script></body></html>
"""


READER_PDF_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>阅读 PDF</title>
<style>
  body, html { margin: 0; height: 100%; }
  iframe { border: 0; width: 100%; height: 100%; }
  header { padding: .5rem 1rem; background: #1f1f1f; color: #ddd;
           font-family: -apple-system, sans-serif; }
  header a { color: #aaa; text-decoration: none; }
</style></head>
<body style="display:flex;flex-direction:column;height:100vh;">
<header><a href="/">🏠</a> <a href="/book/{{ id }}">← 详情</a></header>
<iframe src="/file/{{ id }}#view=FitH"></iframe>
</body></html>
"""


READER_TXT_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>阅读 TXT</title>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; background: #f5f5f5; color: #222; height: 100vh;
         display: flex; flex-direction: column; font-family: -apple-system, sans-serif; }
  body.dark { background: #2a2a2a; color: #ddd; }
  header { padding: .5rem 1rem; background: #1f1f1f; display: flex; gap: .6rem;
           align-items: center; border-bottom: 1px solid #333; flex-shrink: 0; }
  header a { color: #aaa; text-decoration: none; }
  button { padding: .35rem .7rem; background: #444; color: #ddd; border: 0;
           border-radius: 4px; cursor: pointer; font-size: .85rem; }
  button.active { background: #666; }
  #content { flex: 1; overflow-y: auto; padding: 2rem 1rem; }
  #text { max-width: 800px; margin: 0 auto; white-space: pre-wrap; line-height: 1.8;
          word-break: break-word; font-size: 16px; }
  #text.sz-sm { font-size: 13px; }
  #text.sz-md { font-size: 16px; }
  #text.sz-lg { font-size: 20px; }
  #save-indicator { font-size: .72rem; color: #666; }
  /* Shared side panel */
  .np, .bp { position:fixed; right:0; top:0; bottom:0; width:290px; background:#fff; color:#222;
             border-left:2px solid #333; z-index:50; display:flex; flex-direction:column;
             box-shadow:-4px 0 20px rgba(0,0,0,.3); }
  .np-hd, .bp-hd { padding:.65rem 1rem; background:#1f1f1f; color:#ddd; display:flex;
                   justify-content:space-between; align-items:center; flex-shrink:0; font-size:.9rem; }
  .np-body, .bp-body { flex:1; overflow-y:auto; padding:.6rem; }
  .np-foot, .bp-foot { padding:.65rem; border-top:1px solid #e8e6df; flex-shrink:0; }
  .ni { background:#fffdf5; border:1px solid #f0e8c0; border-radius:5px;
        padding:.55rem; margin-bottom:.5rem; }
  .ni .nt { font-size:.82rem; line-height:1.55; white-space:pre-wrap; }
  .ni .nm { font-size:.7rem; color:#aaa; margin-top:.3rem; }
  .nt-area { width:100%; min-height:75px; padding:.45rem; border:1px solid #ccc;
             border-radius:5px; font-size:.85rem; resize:vertical; font-family:inherit; }
  .save-btn { margin-top:.4rem; padding:.35rem .8rem; background:#2d6cdf; color:#fff;
              border:0; border-radius:4px; cursor:pointer; font-size:.85rem; }
  .cp-wrap { display:flex; gap:.4rem; margin-bottom:.5rem; }
  .cp-dot { width:22px; height:22px; border-radius:50%; cursor:pointer; display:inline-block;
            outline:2px solid transparent; outline-offset:2px; flex-shrink:0; }
  .bkm-in { width:100%; box-sizing:border-box; padding:.4rem; border:1px solid #ccc;
            border-radius:5px; font-size:.82rem; margin:.3rem 0; font-family:inherit; }
  .bkm-row { display:flex; align-items:center; gap:.45rem; padding:.4rem .2rem;
             border-bottom:1px solid #f0ede8; }
  .bk-dot { width:12px; height:12px; border-radius:50%; flex-shrink:0; }
  .bkm-info { flex:1; min-width:0; }
  .bkm-lbl { font-size:.82rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .bkm-pos { font-size:.7rem; color:#aaa; }
  .bkm-go { background:none; border:0; color:#2d6cdf; cursor:pointer; font-size:.78rem; padding:.1rem .3rem; flex-shrink:0; }
  .bkm-x  { background:none; border:0; color:#bbb; cursor:pointer; font-size:.9rem; padding:.1rem .3rem; flex-shrink:0; }
  .tp { position:fixed; left:0; top:0; bottom:0; width:280px; background:#fff; color:#222;
        border-right:2px solid #333; z-index:50; display:flex; flex-direction:column;
        box-shadow:4px 0 20px rgba(0,0,0,.3); }
  .tp-hd { padding:.65rem 1rem; background:#1f1f1f; color:#ddd; display:flex;
           justify-content:space-between; align-items:center; flex-shrink:0; font-size:.9rem; }
  .tp-body { flex:1; overflow-y:auto; }
  .tc-item { padding:.45rem .7rem; cursor:pointer; font-size:.82rem;
             border-bottom:1px solid #f0ede8; line-height:1.4; }
  .tc-item:hover { background:#f5f3ee; }
  @media(max-width:540px){
    header { gap:.3rem; padding:.4rem .6rem; }
    button { padding:.28rem .5rem; font-size:.75rem; }
    .sz-label { display:none; }
  }
</style></head>
<body>
<header>
  <a href="/">🏠</a>
  <a href="/book/{{ id }}">← 详情</a>
  <span class="sz-label" style="margin-left:.5rem;color:#888;font-size:.8rem;">字号</span>
  <button id="bsm">小</button>
  <button id="bmd" class="active">中</button>
  <button id="blg">大</button>
  <button id="btheme" style="margin-left:.3rem;">深色</button>
  <button onclick="toggleToc()" title="目录" style="margin-left:auto;">☰</button>
  <button onclick="toggleNotes()" title="笔记">📝</button>
  <button onclick="toggleBkm()" title="书签">🔖</button>
  <span id="save-indicator"></span>
</header>
<div id="content"><div id="text">加载中…</div></div>
<!-- TOC panel -->
<div class="tp" id="tp" style="display:none;">
  <div class="tp-hd">☰ 目录
    <button onclick="toggleToc()" style="background:none;border:0;color:#aaa;cursor:pointer;font-size:1.2rem;line-height:1;">×</button>
  </div>
  <div class="tp-body" id="tp-body"><div style="color:#aaa;font-size:.82rem;padding:.6rem;">加载中…</div></div>
</div>
<!-- Notes panel -->
<div class="np" id="np" style="display:none;">
  <div class="np-hd">📝 笔记
    <button onclick="toggleNotes()" style="background:none;border:0;color:#aaa;cursor:pointer;font-size:1.2rem;line-height:1;">×</button>
  </div>
  <div class="np-body" id="np-body"><div style="color:#aaa;font-size:.82rem;padding:.3rem;">加载中…</div></div>
  <div class="np-foot">
    <textarea class="nt-area" id="nt-input" placeholder="摘录或笔记（自动记录当前阅读位置）"></textarea>
    <button class="save-btn" onclick="saveNote()">保存笔记</button>
  </div>
</div>
<!-- Bookmark panel -->
<div class="bp" id="bp" style="display:none;">
  <div class="bp-hd">🔖 书签
    <button onclick="toggleBkm()" style="background:none;border:0;color:#aaa;cursor:pointer;font-size:1.2rem;line-height:1;">×</button>
  </div>
  <div class="bp-body">
    <div style="padding:.6rem;border-bottom:1px solid #f0ede8;margin-bottom:.4rem;">
      <div style="font-size:.75rem;color:#888;margin-bottom:.35rem;">选颜色</div>
      <div class="cp-wrap">
        <span class="cp-dot" data-c="red"    style="background:#e74c3c;" onclick="selColor(this)"></span>
        <span class="cp-dot" data-c="orange" style="background:#f39c12;outline-color:#333;" onclick="selColor(this)"></span>
        <span class="cp-dot" data-c="green"  style="background:#27ae60;" onclick="selColor(this)"></span>
        <span class="cp-dot" data-c="blue"   style="background:#3498db;" onclick="selColor(this)"></span>
        <span class="cp-dot" data-c="purple" style="background:#9b59b6;" onclick="selColor(this)"></span>
      </div>
      <input class="bkm-in" id="bkm-in" placeholder="书签备注（可选）">
      <button class="save-btn" style="width:100%;" onclick="addBkm()">添加书签到当前位置</button>
    </div>
    <div id="bp-list"></div>
  </div>
</div>
<script>
const BOOK_ID = {{ id }};
const UID = localStorage.getItem('books_uid');
const textEl = document.getElementById('text');
const contentEl = document.getElementById('content');
const body = document.body;
let dark = false;
let saveTimer = null;
let totalLen = 0;
let notesOpen = false;
let tocItems = [], tocOpen = false;

document.getElementById('btheme').onclick = function() {
  dark = !dark;
  body.classList.toggle('dark', dark);
  this.textContent = dark ? '浅色' : '深色';
};
function setSz(sz) {
  textEl.className = 'sz-' + sz;
  ['sm','md','lg'].forEach(s => document.getElementById('b'+s).classList.toggle('active', s===sz));
}
document.getElementById('bsm').onclick = () => setSz('sm');
document.getElementById('bmd').onclick = () => setSz('md');
document.getElementById('blg').onclick = () => setSz('lg');

async function load() {
  const resp = await fetch('/file/{{ id }}');
  if (!resp.ok) { textEl.textContent = '文件加载失败'; return; }
  const buf = await resp.arrayBuffer();
  let text;
  try { text = new TextDecoder('utf-8', {fatal:true}).decode(buf); }
  catch { try { text = new TextDecoder('gbk', {fatal:true}).decode(buf); }
          catch { text = new TextDecoder('latin-1').decode(buf); } }
  textEl.textContent = text;
  totalLen = text.length;
  tocItems = buildTxtToc(text);
  if (UID) {
    try {
      const r = await fetch('/api/user/' + UID + '/history/' + BOOK_ID);
      const h = await r.json();
      if (h && h.progress_pct > 0) {
        contentEl.scrollTop = h.progress_pct * (contentEl.scrollHeight - contentEl.clientHeight);
      }
    } catch(e) {}
  }
}
function buildTxtToc(text) {
  const pat = /^(第[〇一二三四五六七八九十百千万\\d零]+[章节回篇集卷][^\\n]{0,30}|Chapter\\s+\\d+[^\\n]{0,30}|CHAPTER\\s+\\d+[^\\n]{0,30})$/m;
  const lines = text.split('\n');
  let offset = 0;
  const items = [];
  for (const line of lines) {
    const t = line.trim();
    if (t && pat.test(t) && items.length < 200) items.push({label:t, pct:offset/text.length});
    offset += line.length + 1;
  }
  if (!items.length) {
    return ['开头','10%','20%','30%','40%','50%','60%','70%','80%','90%'].map((label,i)=>({label,pct:i*0.1}));
  }
  return items;
}

contentEl.addEventListener('scroll', () => {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveProgress, 5000);
});
async function saveProgress() {
  if (!UID) return;
  const maxScroll = Math.max(1, contentEl.scrollHeight - contentEl.clientHeight);
  const pct = Math.min(1, contentEl.scrollTop / maxScroll);
  try {
    await fetch('/api/user/' + UID + '/history', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({book_id:BOOK_ID, progress_pct:pct, last_position:String(Math.round(pct*totalLen))})
    });
    const ind = document.getElementById('save-indicator');
    ind.textContent = '已保存'; setTimeout(() => ind.textContent='', 2000);
  } catch(e) {}
}
function getCurrentPos() {
  const maxScroll = Math.max(1, contentEl.scrollHeight - contentEl.clientHeight);
  return (contentEl.scrollTop/maxScroll*100).toFixed(1) + '%';
}

// TOC panel
function toggleToc() {
  tocOpen = !tocOpen;
  document.getElementById('tp').style.display = tocOpen ? 'flex' : 'none';
  if (tocOpen) loadToc();
}
function loadToc() {
  const el = document.getElementById('tp-body');
  if (!tocItems.length) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.6rem;">暂无目录</div>'; return; }
  el.innerHTML = tocItems.map((item, i) =>
    '<div class="tc-item" onclick="jumpChapter('+i+')">' + en(item.label) + '</div>'
  ).join('');
}
function jumpChapter(idx) {
  const item = tocItems[idx];
  const maxScroll = Math.max(1, contentEl.scrollHeight - contentEl.clientHeight);
  contentEl.scrollTop = item.pct * maxScroll;
  toggleToc();
}

// Notes panel
function toggleNotes() {
  notesOpen = !notesOpen;
  document.getElementById('np').style.display = notesOpen ? 'flex' : 'none';
  if (notesOpen) loadNotes();
}
async function loadNotes() {
  const el = document.getElementById('np-body');
  if (!UID) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.3rem;">请先在首页激活账号</div>'; return; }
  try {
    const r = await fetch('/api/user/'+UID+'/notes/'+BOOK_ID);
    const d = await r.json();
    const notes = d.notes || [];
    if (!notes.length) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.3rem;">暂无笔记，在下方输入保存</div>'; return; }
    el.innerHTML = notes.map(n =>
      '<div class="ni"><div class="nt">'+en(n.text)+'</div>' +
      '<div class="nm">'+fd(n.updated_at||n.created_at)+
      (n.position ? ' · '+en(n.position):'') +
      ' <button onclick="delNote('+n.id+')" style="background:none;border:0;color:#bbb;cursor:pointer;font-size:.75rem;">删除</button></div></div>'
    ).join('');
  } catch(e) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.3rem;">加载失败</div>'; }
}
async function saveNote() {
  if (!UID) return;
  const text = document.getElementById('nt-input').value.trim();
  if (!text) return;
  await fetch('/api/user/'+UID+'/note', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({book_id:BOOK_ID, text, position:getCurrentPos()})
  });
  document.getElementById('nt-input').value='';
  loadNotes();
}
async function delNote(id) {
  if (!UID) return;
  await fetch('/api/user/'+UID+'/note/'+id, {method:'DELETE'});
  loadNotes();
}
function en(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function fd(ts){return ts?new Date(ts*1000).toLocaleDateString('zh-CN'):'';}

// ── Bookmarks ─────────────────────────────────────────────────────────────────
const CMAP = {red:'#e74c3c',orange:'#f39c12',green:'#27ae60',blue:'#3498db',purple:'#9b59b6'};
let bkmColor = 'orange', bkmPositions = [], bkmOpen = false;
function selColor(el) {
  bkmColor = el.dataset.c;
  document.querySelectorAll('.cp-dot').forEach(d => d.style.outlineColor = 'transparent');
  el.style.outlineColor = '#333';
}
function toggleBkm() {
  bkmOpen = !bkmOpen;
  document.getElementById('bp').style.display = bkmOpen ? 'flex' : 'none';
  if (bkmOpen) { if (notesOpen) toggleNotes(); loadBkm(); }
}
async function loadBkm() {
  const el = document.getElementById('bp-list');
  if (!UID) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.3rem;">请先在首页激活账号</div>'; return; }
  try {
    const r = await fetch('/api/user/'+UID+'/bookmarks/'+BOOK_ID);
    const d = await r.json();
    const bkms = d.bookmarks || [];
    bkmPositions = bkms.map(b => b.position||'');
    if (!bkms.length) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.3rem;">暂无书签，在上方添加</div>'; return; }
    el.innerHTML = bkms.map((b,i) => {
      const col = CMAP[b.color]||CMAP.orange;
      return '<div class="bkm-row">' +
        '<span class="bk-dot" style="background:'+col+'"></span>' +
        '<div class="bkm-info">' +
          '<div class="bkm-lbl">'+en(b.label||'书签')+'</div>' +
          (b.position?'<div class="bkm-pos">'+en(b.position)+'</div>':'') +
        '</div>' +
        '<button class="bkm-go" onclick="jumpBkm('+i+')">跳转</button>' +
        '<button class="bkm-x" onclick="delBkm('+b.id+')">×</button>' +
      '</div>';
    }).join('');
  } catch(e) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.3rem;">加载失败</div>'; }
}
function getCurrentBkmPos() {
  const max = Math.max(1, contentEl.scrollHeight - contentEl.clientHeight);
  return (contentEl.scrollTop / max * 100).toFixed(1) + '%';
}
async function addBkm() {
  if (!UID) return;
  const label = document.getElementById('bkm-in').value.trim() || getCurrentBkmPos();
  await fetch('/api/user/'+UID+'/bookmark', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({book_id:BOOK_ID, position:getCurrentBkmPos(), label, color:bkmColor})
  });
  document.getElementById('bkm-in').value='';
  loadBkm();
}
async function delBkm(id) {
  if (!UID) return;
  await fetch('/api/user/'+UID+'/bookmark/'+id, {method:'DELETE'});
  loadBkm();
}
function jumpBkm(idx) {
  const pos = bkmPositions[idx];
  if (!pos) return;
  const pct = parseFloat(pos) / 100;
  contentEl.scrollTop = pct * Math.max(1, contentEl.scrollHeight - contentEl.clientHeight);
}

window.addEventListener('beforeunload', () => { clearTimeout(saveTimer); saveProgress(); });
load();
</script></body></html>
"""


READER_DOCX_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>阅读 DOCX</title>
<script src="https://cdn.jsdelivr.net/npm/mammoth@1.8.0/mammoth.browser.min.js"></script>
<style>
  * { box-sizing: border-box; }
  body { margin: 0; background: #2a2a2a; color: #ddd; height: 100vh;
         display: flex; flex-direction: column; font-family: -apple-system, sans-serif; }
  header { padding: .5rem 1rem; background: #1f1f1f; display: flex; gap: .8rem;
           align-items: center; border-bottom: 1px solid #333; flex-shrink: 0; }
  header a { color: #aaa; text-decoration: none; }
  button { padding: .35rem .7rem; background: #444; color: #ddd; border: 0;
           border-radius: 4px; cursor: pointer; font-size: .85rem; }
  #content { flex: 1; overflow-y: auto; padding: 2rem 1rem; background: #f5f5f5; }
  #doc { max-width: 900px; margin: 0 auto; background: #fff; padding: 2.5rem 3rem;
         border-radius: 4px; color: #222; font-size: 15px; line-height: 1.8; }
  #doc h1, #doc h2, #doc h3 { margin-top: 1.5em; }
  #doc p { margin: .6em 0; }
  #doc table { border-collapse: collapse; width: 100%; }
  #doc td, #doc th { border: 1px solid #ccc; padding: .4rem .6rem; }
  .err { color: #c44; text-align: center; padding: 3rem; font-size: 1rem; }
  .np { position:fixed; right:0; top:0; bottom:0; width:290px; background:#fff; color:#222;
        border-left:2px solid #333; z-index:50; display:flex; flex-direction:column;
        box-shadow:-4px 0 20px rgba(0,0,0,.3); }
  .np-hd { padding:.65rem 1rem; background:#1f1f1f; color:#ddd; display:flex;
           justify-content:space-between; align-items:center; flex-shrink:0; font-size:.9rem; }
  .np-body { flex:1; overflow-y:auto; padding:.6rem; }
  .np-foot { padding:.65rem; border-top:1px solid #e8e6df; flex-shrink:0; }
  .ni { background:#fffdf5; border:1px solid #f0e8c0; border-radius:5px; padding:.55rem; margin-bottom:.5rem; }
  .ni .nt { font-size:.82rem; line-height:1.55; white-space:pre-wrap; }
  .ni .nm { font-size:.7rem; color:#aaa; margin-top:.3rem; }
  .nt-area { width:100%; min-height:75px; padding:.45rem; border:1px solid #ccc;
             border-radius:5px; font-size:.85rem; resize:vertical; font-family:inherit; }
  .save-btn { margin-top:.4rem; padding:.35rem .8rem; background:#2d6cdf; color:#fff;
              border:0; border-radius:4px; cursor:pointer; font-size:.85rem; }
  .tp { position:fixed; left:0; top:0; bottom:0; width:280px; background:#fff; color:#222;
        border-right:2px solid #333; z-index:50; display:flex; flex-direction:column;
        box-shadow:4px 0 20px rgba(0,0,0,.3); }
  .tp-hd { padding:.65rem 1rem; background:#1f1f1f; color:#ddd; display:flex;
           justify-content:space-between; align-items:center; flex-shrink:0; font-size:.9rem; }
  .tp-body { flex:1; overflow-y:auto; }
  .tc-item { padding:.45rem .7rem; cursor:pointer; font-size:.82rem;
             border-bottom:1px solid #f0ede8; line-height:1.4; }
  .tc-item:hover { background:#f5f3ee; }
  @media(max-width:540px){
    header { gap:.4rem; padding:.4rem .6rem; }
    button { padding:.3rem .5rem; font-size:.78rem; }
    #doc { padding:.8rem; font-size:.9rem; }
  }
</style></head>
<body>
<header>
  <a href="/">🏠</a>
  <a href="/book/{{ id }}">← 详情</a>
  <button onclick="toggleToc()" title="目录" style="margin-left:auto;">☰</button>
  <button onclick="toggleNotes()" title="笔记">📝</button>
</header>
<div id="content"><div id="doc">加载中…</div></div>
<div class="tp" id="tp" style="display:none;">
  <div class="tp-hd">☰ 目录
    <button onclick="toggleToc()" style="background:none;border:0;color:#aaa;cursor:pointer;font-size:1.2rem;line-height:1;">×</button>
  </div>
  <div class="tp-body" id="tp-body"><div style="color:#aaa;font-size:.82rem;padding:.6rem;">加载中…</div></div>
</div>
<div class="np" id="np" style="display:none;">
  <div class="np-hd">📝 笔记
    <button onclick="toggleNotes()" style="background:none;border:0;color:#aaa;cursor:pointer;font-size:1.2rem;line-height:1;">×</button>
  </div>
  <div class="np-body" id="np-body"></div>
  <div class="np-foot">
    <textarea class="nt-area" id="nt-input" placeholder="摘录或笔记…"></textarea>
    <button class="save-btn" onclick="saveNote()">保存笔记</button>
  </div>
</div>
<script>
const BOOK_ID = {{ id }};
const UID = localStorage.getItem('books_uid');
let notesOpen = false;
let tocItems = [], tocOpen = false;

async function load() {
  const docEl = document.getElementById('doc');
  try {
    const resp = await fetch('/file/{{ id }}');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const buf = await resp.arrayBuffer();
    const result = await mammoth.convertToHtml({arrayBuffer: buf});
    docEl.innerHTML = result.value || '<p class="err">文档内容为空</p>';
    tocItems = buildDocxToc(docEl);
  } catch(e) {
    docEl.innerHTML = '<p class="err">文档转换失败：' + e.message + '</p>';
  }
}
function buildDocxToc(docEl) {
  const headings = docEl.querySelectorAll('h1,h2,h3');
  if (!headings.length) return [];
  return Array.from(headings).map((el, i) => {
    const id = 'h-' + i;
    el.id = id;
    const depth = parseInt(el.tagName[1]) - 1;
    return {label: el.textContent.trim(), id, depth};
  });
}
function toggleToc() {
  tocOpen = !tocOpen;
  document.getElementById('tp').style.display = tocOpen ? 'flex' : 'none';
  if (tocOpen) loadToc();
}
function loadToc() {
  const el = document.getElementById('tp-body');
  if (!tocItems.length) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.6rem;">暂无目录</div>'; return; }
  el.innerHTML = tocItems.map((item, i) =>
    '<div class="tc-item" style="padding-left:'+(0.7+item.depth*1.1)+'rem" onclick="jumpChapter('+i+')">' + en(item.label||'标题') + '</div>'
  ).join('');
}
function jumpChapter(idx) {
  const item = tocItems[idx];
  const target = document.getElementById(item.id);
  if (target) target.scrollIntoView({behavior:'smooth', block:'start'});
  toggleToc();
}
function toggleNotes() {
  notesOpen = !notesOpen;
  document.getElementById('np').style.display = notesOpen ? 'flex' : 'none';
  if (notesOpen) loadNotes();
}
async function loadNotes() {
  const el = document.getElementById('np-body');
  if (!UID) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.3rem;">请先在首页激活账号</div>'; return; }
  try {
    const r = await fetch('/api/user/'+UID+'/notes/'+BOOK_ID);
    const d = await r.json();
    const notes = d.notes || [];
    if (!notes.length) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.3rem;">暂无笔记</div>'; return; }
    el.innerHTML = notes.map(n =>
      '<div class="ni"><div class="nt">'+en(n.text)+'</div>' +
      '<div class="nm">'+fd(n.updated_at||n.created_at)+
      ' <button onclick="delNote('+n.id+')" style="background:none;border:0;color:#bbb;cursor:pointer;font-size:.75rem;">删除</button></div></div>'
    ).join('');
  } catch(e) {}
}
async function saveNote() {
  if (!UID) return;
  const text = document.getElementById('nt-input').value.trim();
  if (!text) return;
  await fetch('/api/user/'+UID+'/note', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({book_id:BOOK_ID, text, position:''})
  });
  document.getElementById('nt-input').value='';
  loadNotes();
}
async function delNote(id) {
  if (!UID) return;
  await fetch('/api/user/'+UID+'/note/'+id, {method:'DELETE'});
  loadNotes();
}
function en(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function fd(ts){return ts?new Date(ts*1000).toLocaleDateString('zh-CN'):'';}
load();
</script></body></html>
"""


READER_MOBI_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>阅读</title>
<script src="https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/epubjs@0.3.93/dist/epub.min.js"></script>
<style>
  body { margin: 0; background: #2a2a2a; color: #ddd; height: 100vh;
         display: flex; flex-direction: column; font-family: -apple-system, sans-serif; }
  header { padding: .5rem 1rem; background: #1f1f1f; display: flex; gap: .8rem;
           align-items: center; border-bottom: 1px solid #333; }
  header a { color: #aaa; text-decoration: none; }
  #converting { font-size: .78rem; color: #888; }
  #viewer { flex: 1; background: #fff; color: #222; overflow: hidden; }
  button { padding: .4rem .8rem; background: #444; color: #ddd; border: 0;
           border-radius: 4px; cursor: pointer; }
  .hdr-btn { padding: .4rem .8rem; background: #444; color: #ddd !important;
             border-radius: 4px; text-decoration: none !important; }
  #save-indicator { font-size: .72rem; color: #666; }
  /* Seek bar (inline in header) */
  #seek-inline { flex:1; display:flex; align-items:center; gap:.5rem; min-width:80px; }
  #seek-bar { flex:1; height:6px; -webkit-appearance:none; appearance:none; background:#555;
              border-radius:3px; outline:none; cursor:pointer; accent-color:#2d6cdf; }
  #seek-bar::-webkit-slider-thumb { -webkit-appearance:none; width:14px; height:14px;
    border-radius:50%; background:#2d6cdf; cursor:grab; }
  #seek-bar::-webkit-slider-runnable-track { border-radius:3px; }
  #loc { font-size:.78rem; color:#888; white-space:nowrap; flex-shrink:0; }
  .np, .bp { position:fixed; right:0; top:0; bottom:0; width:290px; background:#fff; color:#222;
             border-left:2px solid #333; z-index:50; display:flex; flex-direction:column;
             box-shadow:-4px 0 20px rgba(0,0,0,.5); }
  .np-hd, .bp-hd { padding:.65rem 1rem; background:#1f1f1f; color:#ddd; display:flex;
                   justify-content:space-between; align-items:center; flex-shrink:0; font-size:.9rem; }
  .np-body, .bp-body { flex:1; overflow-y:auto; padding:.6rem; }
  .np-foot, .bp-foot { padding:.65rem; border-top:1px solid #e8e6df; flex-shrink:0; }
  .ni { background:#fffdf5; border:1px solid #f0e8c0; border-radius:5px; padding:.55rem; margin-bottom:.5rem; }
  .ni .nt { font-size:.82rem; line-height:1.55; white-space:pre-wrap; }
  .ni .nm { font-size:.7rem; color:#aaa; margin-top:.3rem; }
  .nt-area { width:100%; min-height:75px; padding:.45rem; border:1px solid #ccc;
             border-radius:5px; font-size:.85rem; resize:vertical; font-family:inherit; }
  .save-btn { margin-top:.4rem; padding:.35rem .8rem; background:#2d6cdf; color:#fff;
              border:0; border-radius:4px; cursor:pointer; font-size:.85rem; }
  .cp-wrap { display:flex; gap:.4rem; margin-bottom:.5rem; }
  .cp-dot { width:22px; height:22px; border-radius:50%; cursor:pointer; display:inline-block;
            outline:2px solid transparent; outline-offset:2px; flex-shrink:0; }
  .bkm-in { width:100%; box-sizing:border-box; padding:.4rem; border:1px solid #ccc;
            border-radius:5px; font-size:.82rem; margin:.3rem 0; font-family:inherit; }
  .bkm-row { display:flex; align-items:center; gap:.45rem; padding:.4rem .2rem;
             border-bottom:1px solid #f0ede8; }
  .bk-dot { width:12px; height:12px; border-radius:50%; flex-shrink:0; }
  .bkm-info { flex:1; min-width:0; }
  .bkm-lbl { font-size:.82rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .bkm-pos { font-size:.7rem; color:#aaa; }
  .bkm-go { background:none; border:0; color:#2d6cdf; cursor:pointer; font-size:.78rem; padding:.1rem .3rem; flex-shrink:0; }
  .bkm-x  { background:none; border:0; color:#bbb; cursor:pointer; font-size:.9rem; padding:.1rem .3rem; flex-shrink:0; }
  .tp { position:fixed; left:0; top:0; bottom:0; width:280px; background:#fff; color:#222;
        border-right:2px solid #333; z-index:50; display:flex; flex-direction:column;
        box-shadow:4px 0 20px rgba(0,0,0,.5); }
  .tp-hd { padding:.65rem 1rem; background:#1f1f1f; color:#ddd; display:flex;
           justify-content:space-between; align-items:center; flex-shrink:0; font-size:.9rem; }
  .tp-body { flex:1; overflow-y:auto; }
  .tc-item { padding:.45rem .7rem; cursor:pointer; font-size:.82rem;
             border-bottom:1px solid #f0ede8; line-height:1.4; }
  .tc-item:hover { background:#f5f3ee; }
  #btm-bar { display:none; position:fixed; bottom:0; left:0; right:0;
             background:#1c1c1c; border-top:1px solid #333; padding:.4rem .8rem;
             align-items:center; z-index:4; }
  header.hidden { display:none !important; }
  #btm-bar.hidden { display:none !important; }
  @media(max-width:540px){
    header { gap:.4rem; padding:.4rem .6rem; }
    button, .hdr-btn { padding:.3rem .5rem; font-size:.78rem; }
    header #seek-inline { display:none; }
    #converting { display:none; }
    #btm-bar { display:flex; }
    #viewer { margin-bottom:46px; }
    #seek-bar { touch-action:none; }
    #seek-bar::-webkit-slider-thumb { width:22px; height:22px; }
  }
</style></head>
<body>
<header>
  <a href="/">🏠</a>
  <a href="/book/{{ id }}" class="hdr-btn">详情</a>
  <button onclick="toggleToc()">目录</button>
  <button id="prev">上一页</button>
  <button id="next">下一页</button>
  <button onclick="adjFont(-1)" title="缩小字体">A-</button>
  <button onclick="adjFont(1)" title="放大字体">A+</button>
  <span id="converting">正在通过 calibre 转换…</span>
  <div id="seek-inline">
    <input type="range" id="seek-bar" min="0" max="100" value="0">
    <span id="loc"></span>
  </div>
  <button onclick="toggleNotes()" title="笔记">📝</button>
  <button onclick="toggleBkm()" title="书签">🔖</button>
  <span id="save-indicator" style="font-size:.72rem;color:#666;"></span>
</header>
<div id="viewer"></div>
<div id="btm-bar"></div>
<div class="tp" id="tp" style="display:none;">
  <div class="tp-hd">☰ 目录
    <button onclick="toggleToc()" style="background:none;border:0;color:#aaa;cursor:pointer;font-size:1.2rem;line-height:1;">×</button>
  </div>
  <div class="tp-body" id="tp-body"><div style="color:#aaa;font-size:.82rem;padding:.6rem;">加载中…</div></div>
</div>
<div class="np" id="np" style="display:none;">
  <div class="np-hd">📝 笔记
    <button onclick="toggleNotes()" style="background:none;border:0;color:#aaa;cursor:pointer;font-size:1.2rem;line-height:1;">×</button>
  </div>
  <div class="np-body" id="np-body"></div>
  <div class="np-foot">
    <textarea class="nt-area" id="nt-input" placeholder="摘录或笔记（自动记录当前位置）"></textarea>
    <button class="save-btn" onclick="saveNote()">保存笔记</button>
  </div>
</div>
<div class="bp" id="bp" style="display:none;">
  <div class="bp-hd">🔖 书签
    <button onclick="toggleBkm()" style="background:none;border:0;color:#aaa;cursor:pointer;font-size:1.2rem;line-height:1;">×</button>
  </div>
  <div class="bp-body">
    <div style="padding:.6rem;border-bottom:1px solid #f0ede8;margin-bottom:.4rem;">
      <div style="font-size:.75rem;color:#888;margin-bottom:.35rem;">选颜色</div>
      <div class="cp-wrap">
        <span class="cp-dot" data-c="red"    style="background:#e74c3c;" onclick="selColor(this)"></span>
        <span class="cp-dot" data-c="orange" style="background:#f39c12;outline-color:#333;" onclick="selColor(this)"></span>
        <span class="cp-dot" data-c="green"  style="background:#27ae60;" onclick="selColor(this)"></span>
        <span class="cp-dot" data-c="blue"   style="background:#3498db;" onclick="selColor(this)"></span>
        <span class="cp-dot" data-c="purple" style="background:#9b59b6;" onclick="selColor(this)"></span>
      </div>
      <input class="bkm-in" id="bkm-in" placeholder="书签备注（可选）">
      <button class="save-btn" style="width:100%;" onclick="addBkm()">添加书签到当前位置</button>
    </div>
    <div id="bp-list"></div>
  </div>
</div>
<script>
const BOOK_ID = {{ id }};
const UID = localStorage.getItem('books_uid');
let rendition, book;
let saveTimer = null;
let notesOpen = false;
let tocItems = [], tocOpen = false;
let totalLocs = 0;
const seekBar = document.getElementById('seek-bar');
const fontSizes = ['70%','80%','85%','90%','95%','100%','110%','120%'];
let fontSizeIdx = parseInt(localStorage.getItem('epub_font_idx') || '5');
function adjFont(d) {
  fontSizeIdx = Math.max(0, Math.min(fontSizes.length-1, fontSizeIdx+d));
  localStorage.setItem('epub_font_idx', fontSizeIdx);
  if (rendition) rendition.themes.fontSize(fontSizes[fontSizeIdx]);
}

async function init() {
  const resp = await fetch('/api/epub-proxy/{{ id }}');
  document.getElementById('converting').style.display = 'none';
  if (!resp.ok) {
    document.getElementById('viewer').textContent = '转换失败，请确认服务端已安装 calibre。';
    return;
  }
  const buffer = await resp.arrayBuffer();
  book = ePub(buffer);
  rendition = book.renderTo('viewer', {width:'100%', height:'100%', flow:'paginated', minSpreadWidth: 9999});
  rendition.themes.fontSize(fontSizes[fontSizeIdx]);
  rendition.hooks.content.register(c => {
    const s = c.document.createElement('style');
    s.textContent = 'body{padding-top:1rem!important;padding-bottom:1rem!important;}';
    c.document.head.appendChild(s);
  });
  book.ready.then(() => book.locations.generate(1024).then(() => {
    totalLocs = book.locations.total();
    seekBar.max = totalLocs;
    const curLoc = rendition.currentLocation();
    if (curLoc && curLoc.start) {
      seekBar.value = curLoc.start.location || Math.round((curLoc.start.percentage||0) * totalLocs);
    }
  }));
  let startCfi = null;
  if (UID) {
    try {
      const r = await fetch('/api/user/' + UID + '/history/' + BOOK_ID);
      const h = await r.json();
      if (h && h.last_position && h.last_position.startsWith('epubcfi')) startCfi = h.last_position;
    } catch(e) {}
  }
  rendition.display(startCfi || undefined);
  rendition.on('relocated', loc => {
    const cfi = loc.start.cfi || '';
    const locEl = document.getElementById('loc');
    let bookPct = 0;
    if (totalLocs > 0 && loc.start.location) {
      bookPct = loc.start.location / totalLocs;
      locEl.textContent = loc.start.location + ' / ' + totalLocs + ' 页';
      seekBar.value = loc.start.location;
    } else {
      bookPct = loc.start.percentage || 0;
      locEl.textContent = bookPct > 0 ? Math.round(bookPct * 100) + '%' : '';
      seekBar.value = Math.round(bookPct * 100);
    }
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => saveProgress(cfi, bookPct), 5000);
  });

  book.loaded.navigation.then(nav => {
    const toc = nav.toc || [];
    if (toc.length > 0) {
      tocItems = flattenToc(toc);
    } else {
      tocItems = (book.spine.items || []).slice(0, 30).map((item, i) => ({
        label: '第 ' + (i + 1) + ' 章', href: item.href || '', depth: 0
      }));
    }
  });
}
async function saveProgress(cfi, pct) {
  if (!UID) return;
  try {
    await fetch('/api/user/' + UID + '/history', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({book_id:BOOK_ID, progress_pct:pct, last_position:cfi})
    });
    const ind = document.getElementById('save-indicator');
    ind.textContent = '已保存'; setTimeout(() => ind.textContent='', 2000);
  } catch(e) {}
}
function getCurrentPos() {
  if (!rendition) return '';
  try { const l = rendition.currentLocation(); return l&&l.start?l.start.cfi:''; } catch(e){return '';}
}

// TOC panel
function flattenToc(items, depth) {
  depth = depth || 0;
  const result = [];
  for (const item of (items || [])) {
    result.push({label:(item.label||'').trim(), href:item.href||'', depth});
    if (item.subitems && item.subitems.length) result.push(...flattenToc(item.subitems, depth+1));
  }
  return result;
}
function toggleToc() {
  tocOpen = !tocOpen;
  document.getElementById('tp').style.display = tocOpen ? 'flex' : 'none';
  if (tocOpen) loadToc();
}
function loadToc() {
  const el = document.getElementById('tp-body');
  if (!tocItems.length) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.6rem;">暂无目录</div>'; return; }
  el.innerHTML = tocItems.map((item, i) =>
    '<div class="tc-item" style="padding-left:'+(0.7+item.depth*1.1)+'rem" onclick="jumpChapter('+i+')">'+en(item.label||'章节')+'</div>'
  ).join('');
}
function jumpChapter(idx) {
  const item = tocItems[idx];
  if (item && rendition) rendition.display(item.href);
  toggleToc();
}

function toggleNotes() {
  notesOpen = !notesOpen;
  document.getElementById('np').style.display = notesOpen ? 'flex' : 'none';
  if (notesOpen) loadNotes();
}
async function loadNotes() {
  const el = document.getElementById('np-body');
  if (!UID) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.3rem;">请先在首页激活账号</div>'; return; }
  try {
    const r = await fetch('/api/user/'+UID+'/notes/'+BOOK_ID);
    const d = await r.json();
    const notes = d.notes || [];
    if (!notes.length) { el.innerHTML = '<div style="color:#aaa;font-size:.82rem;padding:.3rem;">暂无笔记</div>'; return; }
    el.innerHTML = notes.map(n =>
      '<div class="ni"><div class="nt">'+en(n.text)+'</div>' +
      '<div class="nm">'+fd(n.updated_at||n.created_at)+
      ' <button onclick="delNote('+n.id+')" style="background:none;border:0;color:#bbb;cursor:pointer;font-size:.75rem;">删除</button></div></div>'
    ).join('');
  } catch(e) {}
}
async function saveNote() {
  if (!UID) return;
  const text = document.getElementById('nt-input').value.trim();
  if (!text) return;
  await fetch('/api/user/'+UID+'/note', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({book_id:BOOK_ID, text, position:getCurrentPos()})
  });
  document.getElementById('nt-input').value='';
  loadNotes();
}
async function delNote(id) {
  if (!UID) return;
  await fetch('/api/user/'+UID+'/note/'+id, {method:'DELETE'});
  loadNotes();
}
function en(s){return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function fd(ts){return ts?new Date(ts*1000).toLocaleDateString('zh-CN'):'';}

// ── Bookmarks ─────────────────────────────────────────────────────────────────
const CMAP = {red:'#e74c3c',orange:'#f39c12',green:'#27ae60',blue:'#3498db',purple:'#9b59b6'};
let bkmColor='orange', bkmPositions=[], bkmOpen=false;
function selColor(el){bkmColor=el.dataset.c;document.querySelectorAll('.cp-dot').forEach(d=>d.style.outlineColor='transparent');el.style.outlineColor='#333';}
function toggleBkm(){bkmOpen=!bkmOpen;document.getElementById('bp').style.display=bkmOpen?'flex':'none';if(bkmOpen){if(notesOpen)toggleNotes();loadBkm();}}
async function loadBkm(){
  const el=document.getElementById('bp-list');
  if(!UID){el.innerHTML='<div style="color:#aaa;font-size:.82rem;padding:.3rem;">请先在首页激活账号</div>';return;}
  try{
    const r=await fetch('/api/user/'+UID+'/bookmarks/'+BOOK_ID);const d=await r.json();
    const bkms=d.bookmarks||[];bkmPositions=bkms.map(b=>b.position||'');
    if(!bkms.length){el.innerHTML='<div style="color:#aaa;font-size:.82rem;padding:.3rem;">暂无书签</div>';return;}
    el.innerHTML=bkms.map((b,i)=>{const col=CMAP[b.color]||CMAP.orange;const isEpub=(b.position||'').startsWith('epubcfi');const pos=isEpub?'':(b.position||'');
      return '<div class="bkm-row"><span class="bk-dot" style="background:'+col+'"></span><div class="bkm-info"><div class="bkm-lbl">'+en(b.label||'书签')+'</div>'+(pos?'<div class="bkm-pos">'+en(pos)+'</div>':'')+'</div><button class="bkm-go" onclick="jumpBkm('+i+')">跳转</button><button class="bkm-x" onclick="delBkm('+b.id+')">×</button></div>';
    }).join('');
  }catch(e){el.innerHTML='<div style="color:#aaa;font-size:.82rem;padding:.3rem;">加载失败</div>';}
}
function getCurrentBkmPos(){if(!rendition)return '';try{const l=rendition.currentLocation();return l&&l.start?l.start.cfi:'';}catch(e){return '';}}
function getCurrentBkmLabel(){if(!rendition)return '';try{const l=rendition.currentLocation();return l&&l.start&&l.start.location?'位置 '+l.start.location:'';}catch(e){return '';}}
async function addBkm(){
  if(!UID)return;let label=document.getElementById('bkm-in').value.trim();const position=getCurrentBkmPos();if(!label)label=getCurrentBkmLabel();
  await fetch('/api/user/'+UID+'/bookmark',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({book_id:BOOK_ID,position,label,color:bkmColor})});
  document.getElementById('bkm-in').value='';loadBkm();
}
async function delBkm(id){if(!UID)return;await fetch('/api/user/'+UID+'/bookmark/'+id,{method:'DELETE'});loadBkm();}
function jumpBkm(idx){const pos=bkmPositions[idx];if(pos&&rendition)rendition.display(pos);}

seekBar.addEventListener('change', () => {
  if (!book || !rendition) return;
  const pct = totalLocs > 0 ? seekBar.value / seekBar.max : seekBar.value / 100;
  try { const cfi = book.locations.cfiFromPercentage(pct); if (cfi) rendition.display(cfi); } catch(e) {}
});
if (window.innerWidth <= 540) {
  const btm = document.getElementById('btm-bar');
  const si = document.getElementById('seek-inline');
  if (btm && si) btm.appendChild(si);
}
if ('ontouchstart' in window) {
  const hd = document.querySelector('header');
  const ov = document.createElement('div');
  const bh = window.innerWidth <= 540 ? 46 : 0;
  ov.style.cssText = 'position:fixed;left:0;right:0;top:0px;bottom:' + bh + 'px;z-index:2;-webkit-tap-highlight-color:transparent;';
  document.body.appendChild(ov);
  let hdrTimer = null;
  function showHdr() {
    if (!hd) return;
    hd.classList.remove('hidden');
    ov.style.top = hd.offsetHeight + 'px';
    clearTimeout(hdrTimer);
    hdrTimer = setTimeout(hideHdr, 3000);
  }
  function hideHdr() {
    if (!hd) return;
    hd.classList.add('hidden');
    ov.style.top = '0px';
  }
  hdrTimer = setTimeout(hideHdr, 2000);
  let tx = 0, ty = 0, moved = false;
  ov.addEventListener('touchstart', e => { tx = e.touches[0].clientX; ty = e.touches[0].clientY; moved = false; }, {passive:true});
  ov.addEventListener('touchmove', e => { if (Math.abs(e.touches[0].clientX-tx)+Math.abs(e.touches[0].clientY-ty) > 8) moved = true; }, {passive:true});
  ov.addEventListener('touchend', e => {
    const dx = e.changedTouches[0].clientX - tx, dy = e.changedTouches[0].clientY - ty;
    const adx = Math.abs(dx), ady = Math.abs(dy);
    if (adx > 40 && adx > ady) { if (dx < 0) rendition && rendition.next(); else rendition && rendition.prev(); }
    else if (ady > 40 && ady > adx) { if (dy < 0) rendition && rendition.next(); else rendition && rendition.prev(); }
    else if (!moved) {
      if (hd && hd.classList.contains('hidden')) showHdr();
      else { if (e.changedTouches[0].clientX > window.innerWidth/2) rendition && rendition.next(); else rendition && rendition.prev(); }
    }
  }, {passive:true});
}
init();
document.getElementById('prev').onclick = () => rendition && rendition.prev();
document.getElementById('next').onclick = () => rendition && rendition.next();
document.addEventListener('keydown', e => {
  if (e.key === 'ArrowRight' && rendition) rendition.next();
  if (e.key === 'ArrowLeft' && rendition) rendition.prev();
});
</script></body></html>
"""


SHELF_HTML = """<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>我的书架</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif;
         margin: 0; background: #f7f6f3; color: #222; }
  header { padding: .75rem 1.5rem; background: #fff; border-bottom: 1px solid #e5e3dd;
           display: flex; align-items: center; gap: 1rem; }
  header a { color: #555; text-decoration: none; font-size: .9rem; }
  header h1 { margin: 0; font-size: 1rem; font-weight: 600; }
  .tabs { display: flex; gap: 0; margin-left: auto; }
  .tab { padding: .35rem .8rem; font-size: .82rem; border: 1px solid #d0cdc4; cursor: pointer;
         background: #fff; color: #555; }
  .tab:first-child { border-radius: 6px 0 0 6px; }
  .tab:last-child { border-radius: 0 6px 6px 0; border-left: 0; }
  .tab.on { background: #2d6cdf; color: #fff; border-color: #2d6cdf; }
  main { max-width: 960px; margin: 1.5rem auto; padding: 0 1.5rem; }
  .summary { font-size: .82rem; color: #888; margin-bottom: 1.2rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 1.2rem; }
  .card { background: #fff; border-radius: 8px; overflow: hidden;
          box-shadow: 0 1px 3px rgba(0,0,0,.06); }
  .card a.cover-wrap { display: block; }
  .card img { width: 100%; aspect-ratio: 5/7; object-fit: cover; display: block; background: #eee; }
  .card .info { padding: .5rem .7rem .7rem; }
  .card .t { font-size: .82rem; font-weight: 500; line-height: 1.3; overflow: hidden;
             display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  .card .a { font-size: .72rem; color: #777; margin-top: .2rem; white-space: nowrap;
             overflow: hidden; text-overflow: ellipsis; }
  .prog-bar { background: #e8e6df; height: 5px; border-radius: 3px; margin: .45rem 0 .2rem; }
  .prog-fill { background: #2d6cdf; height: 100%; border-radius: 3px; max-width: 100%; }
  .prog-fill.done { background: #4caf50; }
  .card .pct { font-size: .72rem; color: #999; }
  .card .date { font-size: .68rem; color: #bbb; margin-top: .1rem; }
  .btns { display: flex; gap: .35rem; margin-top: .5rem; }
  .btn { padding: .28rem .6rem; font-size: .75rem; border-radius: 4px; text-decoration: none;
         background: #2d6cdf; color: #fff; border: 0; cursor: pointer; white-space: nowrap; }
  .btn.sec { background: #eee; color: #444; }
  .empty { text-align: center; color: #888; padding: 5rem 1rem; }
  .empty a { color: #2d6cdf; }
  @media(max-width:600px){
    header { padding:.6rem .9rem; gap:.6rem; flex-wrap:wrap; }
    header h1 { font-size:.9rem; }
    .tabs { margin-left:0; }
    main { padding:0 .8rem; margin:1rem auto; }
    .grid { grid-template-columns:repeat(auto-fill,minmax(130px,1fr)); gap:.8rem; }
  }
</style></head>
<body>
<header>
  <a href="/">← 书库</a>
  <h1>📚 我的书架</h1>
  <div class="tabs">
    <button class="tab on" onclick="setFilter('all')">全部</button>
    <button class="tab" onclick="setFilter('reading')">阅读中</button>
    <button class="tab" onclick="setFilter('done')">已读完</button>
  </div>
</header>
<main>
  <div class="summary" id="summary"></div>
  <div class="grid" id="grid"></div>
  <div class="empty" id="empty" style="display:none;">
    暂无阅读记录，去<a href="/">书库</a>选一本书开始阅读
  </div>
</main>
<script>
const UID = localStorage.getItem('books_uid');
let allBooks = [];
let filterMode = 'all';

async function load() {
  if (!UID) {
    document.getElementById('empty').style.display = 'block';
    document.getElementById('empty').innerHTML = '请先打开<a href="/">书库首页</a>激活账号';
    return;
  }
  try {
    const r = await fetch('/api/user/' + UID + '/history?limit=200');
    const d = await r.json();
    allBooks = d.history || [];
    render();
  } catch(e) {
    document.getElementById('empty').style.display = 'block';
    document.getElementById('empty').textContent = '加载失败，请刷新重试';
  }
}

function setFilter(mode) {
  filterMode = mode;
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('on', ['all','reading','done'][i]===mode));
  render();
}

function render() {
  const books = allBooks.filter(b => {
    const pct = b.progress_pct || 0;
    if (filterMode === 'reading') return pct < 0.95;
    if (filterMode === 'done') return pct >= 0.95;
    return true;
  });
  const grid = document.getElementById('grid');
  const empty = document.getElementById('empty');
  const summary = document.getElementById('summary');
  const done = allBooks.filter(b => (b.progress_pct||0) >= 0.95).length;
  const reading = allBooks.filter(b => (b.progress_pct||0) < 0.95 && (b.progress_pct||0) > 0).length;
  summary.textContent = '共 ' + allBooks.length + ' 本 · 阅读中 ' + reading + ' · 已读完 ' + done;

  if (!books.length) {
    grid.innerHTML = '';
    empty.style.display = 'block';
    if (filterMode === 'reading') empty.innerHTML = '没有阅读中的书籍';
    else if (filterMode === 'done') empty.innerHTML = '还没有读完的书籍';
    else empty.innerHTML = '暂无阅读记录，去<a href="/">书库</a>选一本书开始阅读';
    return;
  }
  empty.style.display = 'none';
  grid.innerHTML = '';
  for (const b of books) {
    const pct = b.progress_pct || 0;
    const pctInt = Math.round(pct * 100);
    const done = pct >= 0.95;
    const lastDate = b.last_read_at ? new Date(b.last_read_at * 1000).toLocaleDateString('zh-CN') : '';
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML =
      '<a class="cover-wrap" href="/book/' + b.book_id + '">' +
        '<img src="/cover/' + b.book_id + '" loading="lazy">' +
      '</a>' +
      '<div class="info">' +
        '<div class="t">' + esc(b.title || '无题') + '</div>' +
        '<div class="a">' + esc(b.author || '佚名') + '</div>' +
        '<div class="prog-bar"><div class="prog-fill' + (done?' done':'') + '" style="width:' + pctInt + '%"></div></div>' +
        '<div class="pct">' + (done ? '✓ 已读完' : pctInt + '%') + '</div>' +
        '<div class="date">' + lastDate + '</div>' +
        '<div class="btns">' +
          '<a class="btn" href="/read/' + b.book_id + '">' + (done ? '重读' : '继续阅读') + '</a>' +
          '<a class="btn sec" href="/book/' + b.book_id + '">详情</a>' +
        '</div>' +
      '</div>';
    grid.appendChild(card);
  }
}

function esc(s) {
  return String(s||'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

load();
</script></body></html>
"""


# ── View routes ────────────────────────────────────────────────────────────────

@app.route("/api/epub-proxy/<int:file_id>")
def epub_proxy(file_id: int):
    if not HAS_CALIBRE:
        return jsonify({"error": "calibre not available"}), 501
    conn = get_db()
    row = conn.execute("SELECT rel_path, ext, source_id FROM files WHERE id = ?", (file_id,)).fetchone()
    if not row:
        abort(404)
    ext = row["ext"].lower()
    if ext not in ("mobi", "azw3", "azw"):
        abort(400)
    cache_path = COVER_DIR / f"{file_id}.converted.epub"
    if cache_path.exists():
        return send_file(cache_path.resolve(), mimetype="application/epub+zip")
    src_path = _resolve_book_path(row["rel_path"], row["source_id"])
    if not src_path.exists():
        abort(404)
    ebook_convert = os.path.join(os.path.dirname(CALIBRE_EBOOK_META), "ebook-convert")
    try:
        result = subprocess.run(
            [ebook_convert, str(src_path), str(cache_path), "--output-profile=default"],
            timeout=120, capture_output=True,
        )
        if result.returncode != 0 or not cache_path.exists():
            return jsonify({"error": "conversion failed"}), 503
    except Exception:
        return jsonify({"error": "conversion failed"}), 503
    return send_file(cache_path.resolve(), mimetype="application/epub+zip")


@app.route("/")
def home():
    return HOME_HTML


@app.route("/shelf")
def shelf_page():
    return SHELF_HTML


@app.route("/book/<int:file_id>")
def book_page(file_id: int):
    conn = get_db()
    row = conn.execute("SELECT id, name FROM files WHERE id = ?", (file_id,)).fetchone()
    if not row:
        abort(404)
    return render_template_string(BOOK_HTML, id=file_id, title=row["name"])


@app.route("/read/<int:file_id>")
def read_page(file_id: int):
    conn = get_db()
    row = conn.execute("SELECT ext FROM files WHERE id = ?", (file_id,)).fetchone()
    if not row:
        abort(404)
    ext = row["ext"].lower()
    if ext == "epub":
        return render_template_string(READER_EPUB_HTML, id=file_id)
    if ext == "pdf":
        return render_template_string(READER_PDF_HTML, id=file_id)
    if ext == "txt":
        return render_template_string(READER_TXT_HTML, id=file_id)
    if ext in ("docx", "doc"):
        return render_template_string(READER_DOCX_HTML, id=file_id)
    if ext in ("mobi", "azw3", "azw"):
        return render_template_string(READER_MOBI_HTML, id=file_id)
    abort(404)


def run(host: str = "0.0.0.0", port: int = 8765):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        index_fields.ensure_columns(conn)
    finally:
        conn.close()
    get_user_db().close()
    ensure_default_source()
    app.run(host=host, port=port, debug=False, threaded=True)
