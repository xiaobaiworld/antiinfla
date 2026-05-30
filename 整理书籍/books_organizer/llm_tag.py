"""阶段 5:LLM 细粒度标签 + 分类纠正。

现有 classify(关键词法)误命中较多(如「五线谱入门」落到 数据科学,
「奥托手绘彩色植物图谱(韩国学论丛)」因「国学」误落 国学经典)。豆瓣 lookup
覆盖率 <1% 且返回 tags=[],拿不到真标签。所以用 LLM 主要从 *标题 + 作者* 出发,
为每本书生成 3-6 个中文细粒度标签,并顺手产出纠正后的 category / category2。

结果写入新列,**不覆盖** classify 的原列,可对比:
- fine_tags:     JSON 数组,如 ["围棋","棋谱","中国流"]
- llm_category:  纠正后的一级分类(8 类之一)
- llm_category2: 纠正后的二级分类
- llm_tagged_at: 时间戳(断点续跑:默认只处理空值)

用法:
    export ANTHROPIC_API_KEY=...
    python -m books_organizer llm-tag --dry-run --limit 5   # 只打印 prompt,不调 API
    python -m books_organizer llm-tag --limit 50            # 试跑 50 本
    python -m books_organizer llm-tag                       # 全量(可中断,重跑续上)

标注在 Mac 上跑(需联网 + key),与 lookup 同侧;web 容器不依赖本模块。
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# 8 个一级分类(与 classify.py 保持一致)
TOP_CATEGORIES = [
    "tech", "business", "humanities", "literature",
    "practical", "education", "reference", "other",
]


def ensure_columns(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(metadata)")}
    if "fine_tags" not in cols:
        conn.execute("ALTER TABLE metadata ADD COLUMN fine_tags TEXT")
    if "llm_category" not in cols:
        conn.execute("ALTER TABLE metadata ADD COLUMN llm_category TEXT")
    if "llm_category2" not in cols:
        conn.execute("ALTER TABLE metadata ADD COLUMN llm_category2 TEXT")
    if "llm_tagged_at" not in cols:
        conn.execute("ALTER TABLE metadata ADD COLUMN llm_tagged_at REAL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_meta_llm_cat2 ON metadata(llm_category2)")
    conn.commit()


# ---- 候选筛选:跳过明显的垃圾文件名标题 ----------------------------------

_CJK = re.compile(r"[一-鿿㐀-䶿]")
_JUNK_EXT = re.compile(r"\.(qxd|indd|tmp|pdg|doc|docx|ppt|pptx|xls|xlsx)\b", re.I)
_ASCII_WORD = re.compile(r"[A-Za-z]{3,}")
# 形如 001-001_CR14_NA_AR_5 / 0002-0033CH01-869761 的排版编号
_CODEY = re.compile(r"^[\W\d_]*([A-Za-z]{1,3}\d|[\d_-]{4,})")


def is_meaningful(title: str | None) -> bool:
    if not title:
        return False
    s = title.strip().strip("\x00").strip()
    if len(s) < 3:
        return False
    if _CJK.search(s):
        return True
    if _JUNK_EXT.search(s):
        return False
    # 纯编号 / 排版代号
    if _CODEY.match(s) and not (" " in s and len(_ASCII_WORD.findall(s)) >= 2):
        return False
    # 至少要有一个像样的英文词
    return bool(_ASCII_WORD.search(s))


def candidates(conn: sqlite3.Connection, force: bool, limit: int | None) -> list[sqlite3.Row]:
    where = "(m.cluster_role IS NULL OR m.cluster_role='primary')"
    if not force:
        where += " AND m.llm_tagged_at IS NULL"
    rows = conn.execute(
        f"""SELECT f.id AS file_id, m.title, m.author, m.category, m.category2,
                   f.rel_path
            FROM metadata m JOIN files f ON f.id = m.file_id
            WHERE {where}
            ORDER BY f.id"""
    ).fetchall()
    out = [r for r in rows if is_meaningful(r["title"])]
    if limit:
        out = out[:limit]
    return out


# ---- Prompt -----------------------------------------------------------------

def build_system_prompt(cat2_vocab: dict[str, list[str]]) -> str:
    vocab_lines = []
    for cat in TOP_CATEGORIES:
        subs = cat2_vocab.get(cat, [])
        vocab_lines.append(f"- {cat}: {', '.join(subs) if subs else '(无现有子类)'}")
    vocab = "\n".join(vocab_lines)
    return f"""你是中文书库的图书馆员,擅长按书名和作者判断一本书的主题。

任务:对每一本书,输出
1) category —— 一级分类,**必须**是这 8 个英文值之一:
   tech(技术/IT/工程), business(商业/经管/金融), humanities(人文/社科/历史/哲学/心理),
   literature(文学/小说/诗歌/散文/网络文学), practical(生活/实用/兴趣爱好/音乐/棋牌/养生),
   education(教育/教材/考试/语言学习), reference(工具书/词典/手册/标准), other(无法判断)
2) category2 —— 二级分类,简短中文词。**优先复用**下方已有子类词;没有合适的再自拟。
3) tags —— 3 到 6 个中文细粒度标签(主题/题材/领域/关键人物),用于跨类检索。
   要点:具体而非笼统(用「价值投资」「围棋」「日本推理」而非「投资」「棋」「小说」);
   不要把书名原样当标签;不要营销词;无法判断主题就给空数组 []。

已有二级分类词表(尽量复用以保持一致):
{vocab}

注意:现有 category2 可能是关键词误判(例如副标题含「国学」就被误分到国学经典),
请以书名真实主题为准,大胆纠正。

输出:严格的 JSON 数组,每个元素对应输入里的一本书,字段
{{"id": <输入的 id>, "category": "...", "category2": "...", "tags": ["...", ...]}}
只输出 JSON,不要解释、不要 markdown 代码块。"""


def build_user_block(batch: list[sqlite3.Row]) -> str:
    items = []
    for r in batch:
        # 路径里常带分类线索(目录名),取末两段做提示
        hint = "/".join(str(r["rel_path"]).split("/")[-3:-1]) if r["rel_path"] else ""
        items.append({
            "id": r["file_id"],
            "title": (r["title"] or "").strip()[:120],
            "author": (r["author"] or "").strip()[:60],
            "path_hint": hint[:80],
            "current_category2": r["category2"] or "",
        })
    return "给这些书分类并打标签,返回 JSON 数组:\n" + json.dumps(items, ensure_ascii=False)


# ---- 调用 + 解析 ------------------------------------------------------------

def _parse_json_array(text: str) -> list[dict[str, Any]]:
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.S)
    start = s.find("[")
    end = s.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON array in response: {text[:200]}")
    return json.loads(s[start:end + 1])


def tag_batch_cli(system: str, batch: list[sqlite3.Row]) -> list[dict[str, Any]]:
    """用 `claude -p` 子进程调用 — 复用 Claude Code 的订阅认证,无需 API key。"""
    import subprocess
    prompt = system + "\n\n" + build_user_block(batch)
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude -p failed: {result.stderr[:300]}")
    return _parse_json_array(result.stdout)


def tag_batch_sdk(client, model: str, system: str, batch: list[sqlite3.Row]) -> list[dict[str, Any]]:
    """用 Anthropic SDK — 需要 ANTHROPIC_API_KEY。"""
    resp = client.messages.create(
        model=model,
        max_tokens=min(8000, 200 + len(batch) * 120),
        system=[{
            "type": "text", "text": system,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": build_user_block(batch)}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    return _parse_json_array(text)


def tag_batch(client, model: str, system: str, batch: list[sqlite3.Row]) -> list[dict[str, Any]]:
    if client == "cli":
        return tag_batch_cli(system, batch)
    return tag_batch_sdk(client, model, system, batch)


def write_results(conn: sqlite3.Connection, results: list[dict[str, Any]]) -> int:
    now = time.time()
    n = 0
    for r in results:
        try:
            fid = int(r["id"])
        except (KeyError, TypeError, ValueError):
            continue
        cat = r.get("category") if r.get("category") in TOP_CATEGORIES else "other"
        cat2 = (r.get("category2") or "").strip()[:40] or None
        tags = r.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        tags = [str(t).strip()[:30] for t in tags if str(t).strip()][:8]
        conn.execute(
            "UPDATE metadata SET fine_tags=?, llm_category=?, llm_category2=?, llm_tagged_at=? "
            "WHERE file_id=?",
            (json.dumps(tags, ensure_ascii=False), cat, cat2, now, fid),
        )
        n += 1
    conn.commit()
    return n


def _cat2_vocab(conn: sqlite3.Connection, top_per_cat: int = 25) -> dict[str, list[str]]:
    vocab: dict[str, list[str]] = {}
    for cat in TOP_CATEGORIES:
        rows = conn.execute(
            "SELECT category2, COUNT(*) n FROM metadata "
            "WHERE category=? AND category2 IS NOT NULL GROUP BY category2 "
            "ORDER BY n DESC LIMIT ?",
            (cat, top_per_cat),
        ).fetchall()
        vocab[cat] = [r[0] for r in rows]
    return vocab


def run(
    conn: sqlite3.Connection,
    model: str = DEFAULT_MODEL,
    limit: int | None = None,
    batch_size: int = 25,
    concurrency: int = 4,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, int]:
    ensure_columns(conn)
    cands = candidates(conn, force=force, limit=limit)
    system = build_system_prompt(_cat2_vocab(conn))
    batches = [cands[i:i + batch_size] for i in range(0, len(cands), batch_size)]
    print(f"llm-tag: {len(cands)} 本待标注 → {len(batches)} 批 (batch={batch_size}, "
          f"model={model}, concurrency={concurrency})", file=sys.stderr)

    if dry_run:
        print("=== SYSTEM PROMPT ===\n" + system, file=sys.stderr)
        if batches:
            print("\n=== 第一批 USER ===\n" + build_user_block(batches[0]), file=sys.stderr)
        return {"candidates": len(cands), "batches": len(batches), "written": 0}

    # 后端选择:优先 SDK(快/并发好),无 key 则 fallback 到 claude -p CLI
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            import anthropic as _anthropic
            client = _anthropic.Anthropic()
            print("backend: anthropic SDK", file=sys.stderr)
        except ImportError:
            client = "cli"
            print("backend: claude -p CLI (SDK not installed)", file=sys.stderr)
    else:
        import shutil
        if not shutil.which("claude"):
            print("error: 需要 ANTHROPIC_API_KEY 或本机安装 claude CLI", file=sys.stderr)
            return {"candidates": len(cands), "batches": len(batches), "written": 0, "error": 1}
        client = "cli"
        # CLI 模式:claude -p 是串行的,并发开多进程反而会被限流,降到 2
        concurrency = min(concurrency, 2)
        print(f"backend: claude -p CLI (no API key), concurrency capped at {concurrency}",
              file=sys.stderr)

    written = 0
    failed = 0
    t0 = time.time()

    def work(batch):
        return tag_batch(client, model, system, batch)

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = {ex.submit(work, b): b for b in batches}
        done = 0
        for fut in as_completed(futs):
            done += 1
            try:
                results = fut.result()
                written += write_results(conn, results)
            except Exception as e:  # noqa: BLE001 — 单批失败不应中断全量
                failed += len(futs[fut])
                print(f"  [batch fail] {e}", file=sys.stderr)
            if done % 10 == 0 or done == len(batches):
                rate = written / max(1e-6, time.time() - t0)
                print(f"  {done}/{len(batches)} 批 · 已写 {written} · {rate:.0f}/s",
                      file=sys.stderr)

    print(f"llm-tag done — written={written} failed={failed} "
          f"in {time.time()-t0:.0f}s", file=sys.stderr)
    return {"candidates": len(cands), "written": written, "failed": failed}
