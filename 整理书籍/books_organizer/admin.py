"""管理后台 Blueprint — /admin

提供书源目录管理、扫描触发、数据库概况。
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path

from flask import Blueprint, abort, jsonify, request

from . import scan as scan_mod
from .paths import BOOKS_ROOT, DB_PATH
from .user_db import get_user_db

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# ── Source path cache (used by web.py for file serving) ──────────────────────
_source_path_cache: dict[int, Path] = {}
_cache_lock = threading.Lock()


def get_source_path(source_id: int) -> Path | None:
    """Return the root Path for a given source_id, with in-memory cache."""
    with _cache_lock:
        if source_id in _source_path_cache:
            return _source_path_cache[source_id]
    conn = get_user_db()
    row = conn.execute("SELECT path FROM book_sources WHERE id=?", (source_id,)).fetchone()
    conn.close()
    if not row:
        return None
    p = Path(row["path"])
    with _cache_lock:
        _source_path_cache[source_id] = p
    return p


def invalidate_source_cache() -> None:
    with _cache_lock:
        _source_path_cache.clear()


def ensure_default_source() -> None:
    """On startup, register current BOOKS_ROOT as the default source if absent."""
    conn = get_user_db()
    try:
        exists = conn.execute(
            "SELECT id FROM book_sources WHERE path=?", (str(BOOKS_ROOT),)
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT OR IGNORE INTO book_sources(name, path, added_at) VALUES(?,?,?)",
                ("默认书库", str(BOOKS_ROOT), int(time.time())),
            )
            conn.commit()
    finally:
        conn.close()


# ── Background scan state ─────────────────────────────────────────────────────
_scan_jobs: dict[int, dict] = {}  # source_id → {status, started_at, finished_at, stats, error}
_scan_lock = threading.Lock()


def _run_scan(sid: int, path: str) -> None:
    started = _scan_jobs[sid]["started_at"]
    try:
        bconn = sqlite3.connect(DB_PATH)
        bconn.row_factory = sqlite3.Row
        stats = scan_mod.scan(bconn, Path(path), source_id=sid, verbose=False)
        book_count = bconn.execute(
            "SELECT COUNT(*) FROM files WHERE source_id=? AND kind='book'", (sid,)
        ).fetchone()[0]
        bconn.close()
        uconn = get_user_db()
        uconn.execute(
            "UPDATE book_sources SET last_scan_at=?, book_count=? WHERE id=?",
            (int(time.time()), book_count, sid),
        )
        uconn.commit()
        uconn.close()
        with _scan_lock:
            _scan_jobs[sid] = {
                "status": "done", "started_at": started,
                "finished_at": time.time(), "stats": stats, "error": None,
            }
    except Exception as exc:
        with _scan_lock:
            _scan_jobs[sid] = {
                "status": "error", "started_at": started,
                "finished_at": time.time(), "stats": None, "error": str(exc),
            }


# ── Routes ────────────────────────────────────────────────────────────────────

@admin_bp.route("/")
def admin_home():
    return ADMIN_HTML


@admin_bp.route("/api/stats")
def api_stats():
    bconn = sqlite3.connect(DB_PATH)
    total_books = bconn.execute(
        "SELECT COUNT(*) FROM files WHERE kind='book'"
    ).fetchone()[0]
    bconn.close()
    uconn = get_user_db()
    source_count = uconn.execute("SELECT COUNT(*) FROM book_sources").fetchone()[0]
    uconn.close()
    try:
        db_bytes = os.path.getsize(DB_PATH)
        db_size = _fmt_size(db_bytes)
    except OSError:
        db_size = "—"
    return jsonify({"total_books": total_books, "source_count": source_count, "db_size": db_size})


@admin_bp.route("/api/sources")
def api_sources():
    conn = get_user_db()
    rows = conn.execute(
        "SELECT id, name, path, added_at, last_scan_at, book_count FROM book_sources ORDER BY id"
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        with _scan_lock:
            job = _scan_jobs.get(r["id"])
        result.append({
            "id": r["id"],
            "name": r["name"],
            "path": r["path"],
            "added_at": r["added_at"],
            "last_scan_at": r["last_scan_at"],
            "book_count": r["book_count"] or 0,
            "scan_status": job["status"] if job else "idle",
        })
    return jsonify(result)


@admin_bp.route("/api/sources", methods=["POST"])
def api_source_add():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    path = (data.get("path") or "").strip()
    if not name or not path:
        return jsonify({"error": "名称和路径不能为空"}), 400
    conn = get_user_db()
    try:
        conn.execute(
            "INSERT INTO book_sources(name, path, added_at) VALUES(?,?,?)",
            (name, path, int(time.time())),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        return jsonify({"error": "路径已存在"}), 409
    finally:
        conn.close()
    invalidate_source_cache()
    return jsonify({"ok": True})


@admin_bp.route("/api/sources/<int:sid>", methods=["DELETE"])
def api_source_delete(sid: int):
    conn = get_user_db()
    conn.execute("DELETE FROM book_sources WHERE id=?", (sid,))
    conn.commit()
    conn.close()
    # Disassociate books from this source (keep records, just clear source_id)
    bconn = sqlite3.connect(DB_PATH)
    bconn.execute("UPDATE files SET source_id=NULL WHERE source_id=?", (sid,))
    bconn.commit()
    bconn.close()
    invalidate_source_cache()
    return jsonify({"ok": True})


@admin_bp.route("/api/sources/<int:sid>/scan", methods=["POST"])
def api_source_scan(sid: int):
    uconn = get_user_db()
    source = uconn.execute(
        "SELECT id, name, path FROM book_sources WHERE id=?", (sid,)
    ).fetchone()
    uconn.close()
    if not source:
        abort(404)
    with _scan_lock:
        job = _scan_jobs.get(sid)
        if job and job["status"] == "running":
            return jsonify({"ok": True, "already_running": True})
        _scan_jobs[sid] = {
            "status": "running", "started_at": time.time(),
            "finished_at": None, "stats": None, "error": None,
        }
    threading.Thread(target=_run_scan, args=(sid, source["path"]), daemon=True).start()
    return jsonify({"ok": True})


@admin_bp.route("/api/sources/<int:sid>/scan-status")
def api_scan_status(sid: int):
    with _scan_lock:
        job = _scan_jobs.get(sid)
    if not job:
        return jsonify({"status": "idle"})
    return jsonify(job)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


# ── Admin HTML ────────────────────────────────────────────────────────────────

ADMIN_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>管理后台 — 书库</title>
<style>
  body { font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;
         margin:0; background:#f7f6f3; color:#222; }
  header { padding:.7rem 1.2rem; background:#fff; border-bottom:1px solid #e5e3dd;
           display:flex; align-items:center; gap:.8rem; }
  header a { color:#555; text-decoration:none; font-size:.9rem; }
  .hdr-title { font-size:1rem; font-weight:600; color:#333; }
  .page { max-width:960px; margin:0 auto; padding:1.2rem 1rem; }
  .card { background:#fff; border:1px solid #e8e6df; border-radius:8px;
          padding:1.1rem 1.3rem; margin-bottom:1.1rem; }
  .card h2 { margin:0 0 .9rem; font-size:.9rem; font-weight:600; color:#666; text-transform:uppercase; letter-spacing:.04em; }
  .stat-row { display:flex; gap:2.5rem; flex-wrap:wrap; }
  .stat .val { font-size:1.9rem; font-weight:700; color:#2d6cdf; }
  .stat .lbl { font-size:.75rem; color:#999; margin-top:.1rem; }
  table { width:100%; border-collapse:collapse; font-size:.875rem; }
  th { padding:.4rem .55rem; text-align:left; color:#999; font-weight:500;
       border-bottom:1px solid #e8e6df; font-size:.75rem; text-transform:uppercase; }
  td { padding:.5rem .55rem; border-bottom:1px solid #f2f0eb; vertical-align:middle; }
  tr:last-child td { border-bottom:none; }
  td.path-cell { font-family:monospace; font-size:.78rem; color:#888; word-break:break-all; }
  .badge { display:inline-block; padding:.17rem .48rem; border-radius:3px; font-size:.72rem; font-weight:500; }
  .badge-idle    { background:#f2f0eb; color:#999; }
  .badge-running { background:#e8f0fe; color:#1a73e8; }
  .badge-done    { background:#e8f5e9; color:#2e7d32; }
  .badge-error   { background:#fce8e6; color:#c62828; }
  .btn { padding:.32rem .75rem; border-radius:5px; border:0; cursor:pointer; font-size:.82rem; font-family:inherit; }
  .btn-scan { background:#2d6cdf; color:#fff; }
  .btn-scan:hover { background:#1e5bc6; }
  .btn-scan:disabled { background:#b0c4ef; cursor:default; }
  .btn-del { background:#fff; color:#c62828; border:1px solid #e0b0ae; }
  .btn-del:hover { background:#fce8e6; }
  .add-row { display:flex; gap:.7rem; align-items:flex-end; flex-wrap:wrap;
             margin-top:1rem; padding-top:1rem; border-top:1px solid #f2f0eb; }
  .field label { display:block; font-size:.75rem; color:#999; margin-bottom:.28rem; }
  .field input { padding:.36rem .6rem; border:1px solid #d0cdc4; border-radius:5px;
                 font-size:.875rem; color:#222; background:#fff; font-family:inherit; }
  .field input.wide { width:220px; }
  .err-msg { color:#c62828; font-size:.8rem; margin-top:.5rem; }
  @media(max-width:600px){
    .stat-row { gap:1.5rem; }
    .stat .val { font-size:1.5rem; }
    table { font-size:.8rem; }
    .field input.wide { width:160px; }
    th:nth-child(3),td:nth-child(3),th:nth-child(4),td:nth-child(4) { display:none; }
  }
</style>
</head>
<body>
<header>
  <a href="/">🏠 首页</a>
  <span style="color:#ccc">›</span>
  <span class="hdr-title">管理后台</span>
</header>
<div class="page">

  <div class="card">
    <h2>概况</h2>
    <div class="stat-row">
      <div class="stat"><div class="val" id="st-books">—</div><div class="lbl">书库总书数</div></div>
      <div class="stat"><div class="val" id="st-srcs">—</div><div class="lbl">书源数</div></div>
      <div class="stat"><div class="val" id="st-db">—</div><div class="lbl">数据库大小</div></div>
    </div>
  </div>

  <div class="card">
    <h2>书源目录</h2>
    <table>
      <thead>
        <tr><th>名称</th><th>路径</th><th>书数</th><th>最近扫描</th><th>状态</th><th></th></tr>
      </thead>
      <tbody id="src-body">
        <tr><td colspan="6" style="color:#bbb;padding:.8rem .55rem;">加载中…</td></tr>
      </tbody>
    </table>
    <div class="add-row">
      <div class="field"><label>书源名称</label><input id="f-name" placeholder="如：NAS 书库"></div>
      <div class="field"><label>容器内绝对路径</label><input id="f-path" class="wide" placeholder="/books"></div>
      <button class="btn btn-scan" onclick="addSource()">添加书源</button>
    </div>
    <div class="err-msg" id="add-err"></div>
  </div>

</div>
<script>
const pollTimers = {};
const fmt = n => n == null ? '—' : Number(n).toLocaleString();
const fmtTime = ts => ts ? new Date(ts*1000).toLocaleString('zh-CN') : '—';
function badge(status) {
  const m = {idle:['idle','空闲'],running:['running','扫描中…'],done:['done','完成'],error:['error','错误']};
  const [c,l] = m[status]||m.idle;
  return `<span class="badge badge-${c}">${l}</span>`;
}

async function loadStats() {
  const d = await fetch('/admin/api/stats').then(r=>r.json());
  document.getElementById('st-books').textContent = fmt(d.total_books);
  document.getElementById('st-srcs').textContent = fmt(d.source_count);
  document.getElementById('st-db').textContent = d.db_size;
}

async function loadSources() {
  const list = await fetch('/admin/api/sources').then(r=>r.json());
  const tb = document.getElementById('src-body');
  if (!list.length) {
    tb.innerHTML = '<tr><td colspan="6" style="color:#bbb;">暂无书源</td></tr>';
    return;
  }
  tb.innerHTML = list.map(s => `
    <tr id="sr-${s.id}">
      <td>${s.name}</td>
      <td class="path-cell">${s.path}</td>
      <td>${fmt(s.book_count)}</td>
      <td style="font-size:.78rem;color:#999;">${fmtTime(s.last_scan_at)}</td>
      <td id="st-${s.id}">${badge(s.scan_status)}</td>
      <td style="display:flex;gap:.35rem;white-space:nowrap;">
        <button class="btn btn-scan" id="sb-${s.id}" onclick="startScan(${s.id})">扫描</button>
        <button class="btn btn-del" onclick="delSource(${s.id})">删除</button>
      </td>
    </tr>`).join('');
  list.forEach(s => { if (s.scan_status==='running') pollScan(s.id); });
}

async function startScan(sid) {
  document.getElementById('sb-'+sid).disabled = true;
  document.getElementById('st-'+sid).innerHTML = badge('running');
  await fetch('/admin/api/sources/'+sid+'/scan', {method:'POST'});
  pollScan(sid);
}

function pollScan(sid) {
  if (pollTimers[sid]) return;
  pollTimers[sid] = setInterval(async () => {
    const d = await fetch('/admin/api/sources/'+sid+'/scan-status').then(r=>r.json());
    document.getElementById('st-'+sid).innerHTML = badge(d.status);
    if (d.status !== 'running') {
      clearInterval(pollTimers[sid]); delete pollTimers[sid];
      const sb = document.getElementById('sb-'+sid);
      if (sb) sb.disabled = false;
      loadSources(); loadStats();
    }
  }, 2000);
}

async function delSource(sid) {
  if (!confirm('删除此书源？已入库的书记录保留，只解除书源关联。')) return;
  await fetch('/admin/api/sources/'+sid, {method:'DELETE'});
  loadSources(); loadStats();
}

async function addSource() {
  const name = document.getElementById('f-name').value.trim();
  const path = document.getElementById('f-path').value.trim();
  const errEl = document.getElementById('add-err');
  errEl.textContent = '';
  if (!name || !path) { errEl.textContent = '名称和路径不能为空'; return; }
  const r = await fetch('/admin/api/sources', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name, path})
  });
  const d = await r.json();
  if (!r.ok) { errEl.textContent = d.error||'添加失败'; return; }
  document.getElementById('f-name').value = '';
  document.getElementById('f-path').value = '';
  loadSources(); loadStats();
}

loadStats(); loadSources();
</script>
</body>
</html>
"""
