"""阶段 4：生成"整理后"的硬链接视图。

不动原文件。在 `<root>/_整理后/` 下生成三个视图：
  - by-author/<作者首字母>/<作者>/<书名>.ext
  - by-category/<分类>/<书名> - <作者>.ext
  - by-title/<首字>/<书名> - <作者>.ext

只处理 metadata.source != 'none' 且至少有 title 的条目。

分类来源：
  1) 在线 lookup 拿到的 tags 前 1 项（如果是常见分类词）
  2) 原始目录顶层名（如 "中外经典名著" / "IT 互联网与计算机技术类"）
  3) 默认 "未分类"

每条记录写入 plan 表（dry-run 优先）；--apply 才真正建立硬链接。
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import time
from pathlib import Path

CATEGORY_KEYWORDS = {
    "小说": "文学小说", "文学": "文学小说", "经典": "文学小说", "诗歌": "文学小说",
    "散文": "文学小说", "戏剧": "文学小说",
    "历史": "历史人文", "传记": "历史人文", "哲学": "历史人文", "人文": "历史人文",
    "政治": "历史人文", "宗教": "历史人文",
    "经济": "商业经管", "管理": "商业经管", "金融": "商业经管", "投资": "商业经管",
    "商业": "商业经管", "营销": "商业经管", "广告": "商业经管",
    "心理": "心理励志", "成长": "心理励志", "励志": "心理励志", "情感": "心理励志",
    "科普": "科学技术", "科学": "科学技术", "数学": "科学技术", "物理": "科学技术",
    "技术": "科学技术", "计算机": "科学技术", "编程": "科学技术", "互联网": "科学技术",
    "AI": "科学技术", "人工智能": "科学技术", "数据": "科学技术",
    "艺术": "艺术设计", "设计": "艺术设计", "音乐": "艺术设计", "电影": "艺术设计",
    "摄影": "艺术设计", "建筑": "艺术设计",
    "生活": "生活方式", "美食": "生活方式", "旅行": "生活方式", "健康": "生活方式",
    "育儿": "生活方式", "家庭": "生活方式",
    "教育": "教育学习", "教材": "教育学习", "学习": "教育学习", "考试": "教育学习",
    "英语": "教育学习", "语言": "教育学习",
    "漫画": "少儿漫画", "绘本": "少儿漫画", "儿童": "少儿漫画", "少儿": "少儿漫画",
    "动漫": "少儿漫画",
}

ILLEGAL_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(s: str | None, fallback: str = "未知", max_len: int = 80) -> str:
    if not s:
        return fallback
    s = ILLEGAL_FS.sub("", s).strip(" .")
    s = re.sub(r"\s+", " ", s)
    if not s:
        return fallback
    if len(s) > max_len:
        s = s[:max_len].rstrip()
    return s


_NATIONALITY_PREFIX = re.compile(r"^[【\[\(（]\s*[^】\]\)）]{1,8}\s*[】\]\)）]\s*")


def primary_author(author: str | None) -> str:
    """取首位作者，去掉 [美]/[日]/(英) 等国籍前缀。"""
    if not author:
        return ""
    first = author.split(";")[0].split(",")[0].strip()
    first = _NATIONALITY_PREFIX.sub("", first).strip()
    return first


def author_initial(author: str) -> str:
    a = primary_author(author)
    if not a:
        return "#"
    c = a[0]
    if c.isascii() and c.isalpha():
        return c.upper()
    return c


def title_initial(title: str) -> str:
    if not title:
        return "#"
    c = title[0]
    if c.isascii() and c.isalpha():
        return c.upper()
    return c


# 这些顶层目录不是真正的"分类"，需要降级用关键词推断
NON_CATEGORY_TOPS = {
    "ForBoox", "test", "_组织后", "_整理后", "_organized",
}


def infer_category(tags_json: str | None, rel_path: str) -> str:
    """优先用用户的顶层目录名（他已经做了简单分类）。"""
    top = rel_path.split("/", 1)[0] if "/" in rel_path else ""

    # 1. 顶层目录就是分类（用户已分类）— 优先用
    if top and top not in NON_CATEGORY_TOPS and not top.startswith("_") and not top.startswith("."):
        return safe_name(top, "未分类", max_len=50)

    # 2. 根目录散文件 / NON_CATEGORY 目录：用豆瓣 tags 推断
    import json as _j
    if tags_json:
        try:
            tags = _j.loads(tags_json)
        except Exception:
            tags = []
        for t in tags:
            for kw, cat in CATEGORY_KEYWORDS.items():
                if kw in t:
                    return cat

    # 3. 还不行：根据书名 + 顶层目录关键词推断
    haystack = (top or "") + " " + rel_path
    for kw, cat in CATEGORY_KEYWORDS.items():
        if kw in haystack:
            return cat

    return "未分类"


def plan_all(conn: sqlite3.Connection, *, min_confidence: float, limit: int | None) -> dict:
    stats = {"planned": 0, "skipped": 0}
    conn.execute("DELETE FROM plan WHERE applied_at IS NULL")
    conn.commit()

    # 只规划 primary（每个 cluster 一条）。variants 通过 web 阅读器查阅。
    q = """
        SELECT f.id, f.rel_path, f.ext, m.title, m.author, m.tags, m.confidence
        FROM files f
        JOIN metadata m ON m.file_id = f.id
        WHERE m.title IS NOT NULL
          AND m.title != ''
          AND m.confidence >= ?
          AND m.source != 'none'
          AND (m.cluster_role = 'primary' OR m.cluster_role IS NULL)
        ORDER BY m.confidence DESC, f.id
    """
    if limit:
        q += f" LIMIT {int(limit)}"

    for row in conn.execute(q, (min_confidence,)):
        title = safe_name(row["title"], "未命名")
        primary = primary_author(row["author"] or "")
        author = safe_name(primary or "佚名", "佚名", max_len=60)
        category = infer_category(row["tags"], row["rel_path"])
        ext = row["ext"]

        a_init = author_initial(row["author"] or "")
        t_init = title_initial(row["title"] or "")

        # 三个视图的目标路径
        for view, target in [
            ("by-author", f"by-author/{a_init}/{author}/{title}.{ext}"),
            ("by-category", f"by-category/{category}/{title} - {author}.{ext}"),
            ("by-title", f"by-title/{t_init}/{title} - {author}.{ext}"),
        ]:
            conn.execute(
                "INSERT INTO plan (file_id, target_rel_path, action, reason) VALUES (?,?,?,?)",
                (row["id"], target, "link", view),
            )
        stats["planned"] += 1

    conn.commit()
    return stats


def apply_all(conn: sqlite3.Connection, root: Path, *, organized_dir: Path) -> dict:
    """实际建立硬链接。同卷下零成本；跨卷会自动回退到 symlink。"""
    stats = {"linked": 0, "exists": 0, "failed": 0, "fallback_symlink": 0}
    organized_dir.mkdir(parents=True, exist_ok=True)

    rows = conn.execute(
        """
        SELECT p.id, p.file_id, p.target_rel_path, p.reason, f.rel_path
        FROM plan p
        JOIN files f ON f.id = p.file_id
        WHERE p.action = 'link' AND p.applied_at IS NULL
        ORDER BY p.id
        """
    ).fetchall()
    total = len(rows)
    print(f"apply: {total} link plans", file=sys.stderr)

    t0 = time.time()
    for i, row in enumerate(rows, 1):
        src = root / row["rel_path"]
        dst = organized_dir / row["target_rel_path"]

        if not src.exists():
            stats["failed"] += 1
            continue
        if dst.exists():
            stats["exists"] += 1
            conn.execute("UPDATE plan SET applied_at = ? WHERE id = ?", (time.time(), row["id"]))
            continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(src, dst)
            stats["linked"] += 1
        except OSError as e:
            # 跨卷或不支持硬链接：fallback symlink
            try:
                os.symlink(src, dst)
                stats["fallback_symlink"] += 1
            except OSError:
                stats["failed"] += 1
                print(f"  ! link failed {row['rel_path']}: {e}", file=sys.stderr)
                continue
        conn.execute("UPDATE plan SET applied_at = ? WHERE id = ?", (time.time(), row["id"]))

        if i % 100 == 0:
            conn.commit()
            dt = time.time() - t0
            print(
                f"  [{i:>5}/{total}] linked={stats['linked']} exists={stats['exists']} "
                f"failed={stats['failed']} sym={stats['fallback_symlink']} ({i/dt:.1f}/s)",
                file=sys.stderr, flush=True,
            )

    conn.commit()
    return stats
