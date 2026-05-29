"""阶段 5：在线阅读站（Flask）。

  python3 -m books_organizer web --port 8765

特性：
- 首页：封面网格，按分类/作者/书名筛选 + 搜索
- 书籍详情：豆瓣简介、元数据、文件信息、"在浏览器打开"
- 浏览器内阅读：EPUB 用 epub.js（CDN），PDF 用 pdf.js（CDN）
- 仅本机/局域网，不做鉴权
"""
from __future__ import annotations

import json
import mimetypes
import sqlite3
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template_string, request, send_file

from . import index_fields
from .paths import BOOKS_ROOT as ROOT, DB_PATH, COVER_DIR

app = Flask(__name__)


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
    # online > embedded > placeholder
    online = COVER_DIR / f"{file_id}.online.jpg"
    if online.exists():
        return send_file(online, mimetype="image/jpeg")
    for ext in ("jpg", "jpeg", "png", "webp"):
        p = COVER_DIR / f"{file_id}.{ext}"
        if p.exists():
            return send_file(p, mimetype=f"image/{ext.replace('jpg','jpeg')}")
    return Response(PLACEHOLDER_SVG, mimetype="image/svg+xml")


@app.route("/file/<int:file_id>")
def raw_file(file_id: int):
    conn = get_db()
    row = conn.execute("SELECT rel_path, ext FROM files WHERE id = ?", (file_id,)).fetchone()
    if not row:
        abort(404)
    path = ROOT / row["rel_path"]
    if not path.exists():
        abort(404)
    mime, _ = mimetypes.guess_type(path.name)
    if not mime:
        mime = "application/octet-stream"
    return send_file(path, mimetype=mime, as_attachment=False,
                     download_name=path.name, conditional=True)


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

    # cluster 其他版本
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


HOME_HTML = """<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>书库</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif;
         margin: 0; background: #f7f6f3; color: #222; }
  header { padding: 1rem 1.5rem; background: #fff; border-bottom: 1px solid #e5e3dd;
           display: flex; gap: 1rem; align-items: center; position: sticky; top: 0; z-index: 10; }
  header h1 { margin: 0; font-size: 1.1rem; font-weight: 600; }
  header input, header select { padding: .4rem .6rem; border: 1px solid #d0cdc4;
           border-radius: 6px; background: #fff; font-size: .9rem; }
  header input[type="search"] { width: 220px; }
  main { padding: 1.5rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
          gap: 1.2rem; }
  .card { background: #fff; border-radius: 8px; overflow: hidden;
          box-shadow: 0 1px 3px rgba(0,0,0,.06); transition: transform .15s; cursor: pointer; }
  .card:hover { transform: translateY(-2px); box-shadow: 0 4px 10px rgba(0,0,0,.08); }
  .card .cov { aspect-ratio: 5/7; background: #eee; width: 100%; object-fit: cover; display: block; }
  .card .meta { padding: .5rem .7rem .7rem; }
  .card .t { font-size: .85rem; font-weight: 500; line-height: 1.3;
             display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
             overflow: hidden; }
  .card .a { font-size: .75rem; color: #777; margin-top: .25rem;
             white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .card .ext { font-size: .65rem; color: #999; text-transform: uppercase; margin-top: .2rem; }
  footer { padding: 2rem; text-align: center; color: #888; font-size: .85rem; }
  .pager { display: flex; gap: .5rem; justify-content: center; padding: 1rem; }
  .pager button { padding: .4rem .8rem; border: 1px solid #d0cdc4; background: #fff;
                  border-radius: 4px; cursor: pointer; }
  .pager button:disabled { opacity: .4; cursor: not-allowed; }
  .empty { text-align: center; color: #888; padding: 4rem; }
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
  <span id="count" style="margin-left:auto; color:#777; font-size:.85rem;"></span>
</header>
<main>
  <div class="grid" id="grid"></div>
  <div class="pager">
    <button id="prev">上一页</button>
    <span id="pageinfo" style="padding:.5rem;"></span>
    <button id="next">下一页</button>
  </div>
</main>
<script>
let page = 1, perPage = 40, total = 0;

const CATEGORY_LABEL = {
  tech: '科技工程', business: '商业管理', humanities: '人文社科',
  literature: '文学艺术', practical: '生活实用', education: '教育学习',
  reference: '工具书', other: '其他',
};
let CATEGORY_TREE = [];
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
    o.textContent = `${CATEGORY_LABEL[c.key] || c.key} (${c.n})`;
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
    o.value = dec.key; o.textContent = `${dec.key}s (${dec.n})`;
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
    o.value = s.key; o.textContent = `${s.key} (${s.n})`;
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
    o.value = sj.key; o.textContent = `${sj.key} (${sj.n})`;
    sel.appendChild(o);
  }
}

async function load() {
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
  const d = await r.json();
  total = d.total;
  document.getElementById('count').textContent = `共 ${total} 本`;
  document.getElementById('pageinfo').textContent =
    `第 ${page} / ${Math.max(1, Math.ceil(total / perPage))} 页`;
  document.getElementById('prev').disabled = page <= 1;
  document.getElementById('next').disabled = page * perPage >= total;
  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  if (d.books.length === 0) {
    grid.innerHTML = '<div class="empty">还没有匹配的书。可能是 extract / lookup 阶段还没跑完。</div>';
    return;
  }
  for (const b of d.books) {
    const a = document.createElement('a');
    a.className = 'card';
    a.href = `/book/${b.id}`;
    a.innerHTML = `
      <img class="cov" src="/cover/${b.id}" loading="lazy">
      <div class="meta">
        <div class="t">${escapeHtml(b.title || '无题')}</div>
        <div class="a">${escapeHtml(b.author || '佚名')}</div>
        <div class="ext">${(b.ext || '').toUpperCase()}</div>
      </div>`;
    grid.appendChild(a);
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

document.getElementById('q').addEventListener('input', debounce(() => { page=1; load(); }, 250));
document.getElementById('category').addEventListener('change', (e) => {
  updateCategory2(e.target.value);
  page=1; load();
});
document.getElementById('category2').addEventListener('change', (e) => {
  updateSubject(document.getElementById('category').value, e.target.value);
  page=1; load();
});
document.getElementById('subject').addEventListener('change', () => { page=1; load(); });
document.getElementById('author').addEventListener('change', () => { page=1; load(); });
document.getElementById('decade').addEventListener('change', () => { page=1; load(); });
document.getElementById('ext').addEventListener('change', () => { page=1; load(); });
document.getElementById('sort').addEventListener('change', () => { page=1; load(); });
document.getElementById('prev').addEventListener('click', () => { page=Math.max(1,page-1); load(); });
document.getElementById('next').addEventListener('click', () => { page+=1; load(); });

function debounce(fn, ms) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

loadFacets().then(load);
</script></body></html>
"""


BOOK_HTML = """<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ title }}</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif;
         margin: 0; background: #f7f6f3; color: #222; }
  header { padding: .75rem 1.5rem; background: #fff; border-bottom: 1px solid #e5e3dd; }
  header a { color: #555; text-decoration: none; }
  .wrap { max-width: 800px; margin: 2rem auto; padding: 0 1.5rem;
          display: grid; grid-template-columns: 200px 1fr; gap: 2rem; }
  .cover { width: 200px; aspect-ratio: 5/7; object-fit: cover; border-radius: 4px;
           box-shadow: 0 2px 6px rgba(0,0,0,.1); background: #eee; }
  .meta h1 { margin: 0 0 .5rem; font-size: 1.5rem; }
  .meta .author { color: #555; margin-bottom: 1rem; }
  .meta dl { margin: 1rem 0; }
  .meta dt { color: #888; font-size: .8rem; margin-top: .5rem; }
  .meta dd { margin: 0; }
  .meta .summary { margin-top: 1.5rem; line-height: 1.7; color: #333;
                   white-space: pre-wrap; word-break: break-word; }
  .actions { margin-top: 1.5rem; display: flex; gap: .75rem; flex-wrap: wrap; }
  .btn { padding: .55rem 1rem; border-radius: 6px; text-decoration: none;
         background: #2d6cdf; color: #fff; font-size: .9rem; }
  .btn.sec { background: #eee; color: #333; }
  .tag { display: inline-block; background: #eee9d8; color: #6b5a1e; padding: .15rem .55rem;
         border-radius: 12px; font-size: .75rem; margin: .15rem .15rem 0 0; }
  @media (max-width: 600px) { .wrap { grid-template-columns: 1fr; } .cover { width: 50%; } }
</style></head>
<body>
<header><a href="/">← 回到书库</a></header>
<div class="wrap" id="root">加载中…</div>
<script>
const id = {{ id }};
async function load() {
  const r = await fetch('/api/book/' + id);
  if (!r.ok) { document.getElementById('root').innerHTML = '<p>未找到</p>'; return; }
  const b = await r.json();
  document.title = b.title || '无题';
  const tags = b.tags ? (() => { try { return JSON.parse(b.tags); } catch { return []; } })() : [];
  const subjects = b.subjects ? (() => { try { return JSON.parse(b.subjects); } catch { return []; } })() : [];
  const ext = (b.ext || '').toLowerCase();
  const canRead = ext === 'epub' || ext === 'pdf';
  const CAT_LABEL = {tech:'科技工程',business:'商业管理',humanities:'人文社科',literature:'文学艺术',practical:'生活实用',education:'教育学习',reference:'工具书',other:'其他'};
  const catLine = b.category
    ? `${esc(CAT_LABEL[b.category] || b.category)}${b.category2 ? ' · ' + esc(b.category2) : ''}`
    : '';
  document.getElementById('root').innerHTML = `
    <img class="cover" src="/cover/${id}">
    <div class="meta">
      <h1>${esc(b.title || '无题')}</h1>
      <div class="author">${esc(b.author || '佚名')}</div>
      ${catLine ? `<div style="margin:.4rem 0;color:#6b5a1e;font-size:.85rem;">${catLine}</div>` : ''}
      <div>${subjects.map(t => `<span class="tag">${esc(t)}</span>`).join('')}</div>
      <div class="actions">
        ${canRead ? `<a class="btn" href="/read/${id}">📖 在线阅读</a>` : ''}
        <a class="btn sec" href="/file/${id}" download>⬇ 下载</a>
      </div>
      <dl>
        ${b.publisher ? `<dt>出版社</dt><dd>${esc(b.publisher)}</dd>` : ''}
        ${b.pubdate ? `<dt>出版日期</dt><dd>${esc(b.pubdate)}</dd>` : ''}
        ${b.isbn ? `<dt>ISBN</dt><dd>${esc(b.isbn)}</dd>` : ''}
        <dt>格式</dt><dd>${esc((b.ext || '').toUpperCase())} · ${fmtSize(b.size || 0)}</dd>
        <dt>路径</dt><dd style="font-size:.8rem;color:#888;">${esc(b.rel_path)}</dd>
        <dt>识别置信度</dt><dd>${(b.confidence * 100).toFixed(0)}%</dd>
      </dl>
      ${b.variants && b.variants.length > 0 ? `
        <h3 style="margin-top:1.5rem;font-size:.95rem;color:#666;">其他版本 / 格式（${b.variants.length}）</h3>
        <ul style="list-style:none;padding:0;margin:.5rem 0;">
          ${b.variants.map(v => `
            <li style="padding:.4rem 0;border-bottom:1px solid #eee;">
              <a href="/book/${v.id}" style="color:#2d6cdf;text-decoration:none;">
                ${(v.ext || '').toUpperCase()}
              </a>
              ${v.publisher ? ' · ' + esc(v.publisher) : ''}
              ${v.pubdate ? ' · ' + esc(v.pubdate) : ''}
              <span style="color:#888;font-size:.8rem;">· ${fmtSize(v.size || 0)}</span>
            </li>`).join('')}
        </ul>` : ''}
      ${b.summary ? `<div class="summary">${esc(b.summary)}</div>` : ''}
    </div>`;
}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function fmtSize(n){const u=['B','KB','MB','GB'];let i=0;while(n>=1024&&i<u.length-1){n/=1024;i++;}return n.toFixed(1)+u[i];}
load();
</script></body></html>
"""


READER_EPUB_HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<title>阅读</title>
<script src="https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/epubjs@0.3.93/dist/epub.min.js"></script>
<style>
  body { margin: 0; background: #2a2a2a; color: #ddd; height: 100vh;
         display: flex; flex-direction: column; font-family: -apple-system, sans-serif; }
  header { padding: .5rem 1rem; background: #1f1f1f; display: flex; gap: 1rem;
           align-items: center; border-bottom: 1px solid #333; }
  header a { color: #aaa; text-decoration: none; }
  #viewer { flex: 1; background: #fff; color: #222; }
  button { padding: .4rem .8rem; background: #444; color: #ddd; border: 0;
           border-radius: 4px; cursor: pointer; }
</style></head>
<body>
<header>
  <a href="/book/{{ id }}">← 详情</a>
  <button id="prev">上一页</button>
  <button id="next">下一页</button>
  <span id="loc" style="margin-left:auto;color:#888;font-size:.85rem;"></span>
</header>
<div id="viewer"></div>
<script>
const book = ePub('/file/{{ id }}');
const rendition = book.renderTo('viewer', { width: '100%', height: '100%', flow: 'paginated' });
rendition.display();
document.getElementById('prev').onclick = () => rendition.prev();
document.getElementById('next').onclick = () => rendition.next();
document.addEventListener('keydown', e => {
  if (e.key === 'ArrowRight') rendition.next();
  if (e.key === 'ArrowLeft') rendition.prev();
});
rendition.on('relocated', loc => {
  document.getElementById('loc').textContent =
    loc.start.location ? `位置 ${loc.start.location}` : '';
});
</script></body></html>
"""


READER_PDF_HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<title>阅读 PDF</title>
<style>
  body, html { margin: 0; height: 100%; }
  iframe { border: 0; width: 100%; height: 100%; }
  header { padding: .5rem 1rem; background: #1f1f1f; color: #ddd;
           font-family: -apple-system, sans-serif; }
  header a { color: #aaa; text-decoration: none; }
</style></head>
<body style="display:flex;flex-direction:column;height:100vh;">
<header><a href="/book/{{ id }}">← 详情</a></header>
<iframe src="/file/{{ id }}#view=FitH"></iframe>
</body></html>
"""


@app.route("/")
def home():
    return HOME_HTML


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
    abort(404)


def run(host: str = "0.0.0.0", port: int = 8765):
    conn = sqlite3.connect(DB_PATH)
    try:
        index_fields.ensure_columns(conn)
    finally:
        conn.close()
    app.run(host=host, port=port, debug=False, threaded=True)
