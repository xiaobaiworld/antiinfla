"""阶段 4.5：去重 / 版本聚类。

把同一本书的不同版本（出版社/年份）、不同格式（EPUB/MOBI/PDF）、重复文件归到同一
cluster。一个 cluster 选一个 primary（链入主视图），其他 variant。

cluster_key = normalize_title|normalize_author
  - 移除 "(套装共N册)", "上下册", "第N版" 等修饰
  - 全角转半角，去标点
  - 作者只取主作者，去 [国籍] 前缀

primary 选择优先级：
  1. 格式：EPUB > MOBI > AZW3 > AZW > PDF（文字版优先扫描版）
  2. confidence 高的
  3. size 大的（信息量通常更多）
  4. file_id 小的（先入库）
"""
from __future__ import annotations

import re
import sqlite3
import sys
import time

from .organize import primary_author

FORMAT_RANK = {
    "epub": 1, "mobi": 2, "azw3": 3, "azw4": 4, "azw": 5,
    "fb2": 6, "prc": 7, "lit": 8,
    "pdf": 10,  # PDF 经常是扫描版，置后
    "txt": 15, "doc": 16, "docx": 16, "rtf": 17, "html": 18, "htm": 18,
}

# 标题里要剥掉的修饰词
_NOISE_PATTERNS = [
    r"[\(（]\s*套装(?:共)?\s*\d+\s*册\s*[\)）]",   # (套装共5册)
    r"[\(（]\s*共\s*\d+\s*册\s*[\)）]",
    r"[\(（]\s*\d+\s*册装\s*[\)）]",
    r"[\(（]\s*上下册?\s*[\)）]",
    r"[\(（]\s*全\d+册?\s*[\)）]",
    r"[\(（]?第\s*\d+\s*版[\)）]?",                   # 第二版
    r"[\(（]?[\dIVX]+(?:st|nd|rd|th)?\s*[Ee]dition[\)）]?",
    r"[\(（]?(?:修订|增订|纪念|典藏|精装|平装|插图|插画|完整|完结|权威|新|经典|双语)版[\)）]?",
    r"[\[【][^\]】]*(?:Z-?Library|zlib|epub|mobi|pdf|version)[^\]】]*[\]】]",
    r"\.\w+$",                                        # 扩展名
    r"\s*[\(（]\s*\d{1,3}\s*[\)）]\s*$",               # 尾部 (1)/(2)/(23) 拷贝标记
    r"\s+\d{1,3}\s*$",                                # 尾部纯数字 "书名 1"
    r"\s*-\s*副本(?:\s*\(?\d+\)?)?\s*$",              # "书名 - 副本" / "书名 - 副本 (1)"
    r"\s*[\(（]\s*副本\s*[\)）]\s*$",                  # "(副本)"
    r"\s*copy(?:\s*\(?\d+\)?)?\s*$",                  # 英文 "copy" / "copy (1)"
]
_NOISE_RE = re.compile("|".join(_NOISE_PATTERNS), re.IGNORECASE)

# 全角→半角映射
_FULL_TO_HALF = {ord("，"): ",", ord("。"): ".", ord("："): ":", ord("；"): ";",
                 ord("！"): "!", ord("？"): "?", ord("（"): "(", ord("）"): ")",
                 ord("【"): "[", ord("】"): "]", ord("　"): " "}


def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    s = title.translate(_FULL_TO_HALF)
    s = _NOISE_RE.sub("", s)
    # 去标点 + 多余空白
    s = re.sub(r"[^\w一-鿿\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def normalize_author(author: str | None) -> str:
    pa = primary_author(author or "")
    if not pa:
        return ""
    pa = pa.translate(_FULL_TO_HALF)
    pa = re.sub(r"[^\w一-鿿\s·]", "", pa)
    return pa.strip().lower()


def compute_cluster_key(title: str | None, author: str | None) -> str | None:
    nt = normalize_title(title)
    na = normalize_author(author)
    if not nt:
        return None
    return f"{nt}|{na}"


def cluster_all(conn: sqlite3.Connection) -> dict:
    """重新计算所有 cluster_key + cluster_role + primary_file_id。"""
    stats = {"books": 0, "clusters": 0, "variants": 0}
    t0 = time.time()

    # 第一遍：计算每本书的 cluster_key
    rows = conn.execute(
        """SELECT m.file_id, m.title, m.author, m.confidence, f.ext, f.size
           FROM metadata m JOIN files f ON f.id = m.file_id
           WHERE m.title IS NOT NULL AND m.title != ''"""
    ).fetchall()

    by_cluster: dict[str, list] = {}
    for r in rows:
        key = compute_cluster_key(r["title"], r["author"])
        if not key:
            continue
        stats["books"] += 1
        by_cluster.setdefault(key, []).append(r)

    stats["clusters"] = len(by_cluster)

    # 第二遍：每个 cluster 选 primary，其余 variant
    cur = conn.cursor()
    for key, members in by_cluster.items():
        def rank(m):
            ext = (m["ext"] or "").lower()
            return (
                FORMAT_RANK.get(ext, 99),
                -float(m["confidence"] or 0),
                -(m["size"] or 0),
                m["file_id"],
            )
        members.sort(key=rank)
        primary = members[0]
        for m in members:
            role = "primary" if m["file_id"] == primary["file_id"] else "variant"
            pfid = None if role == "primary" else primary["file_id"]
            if role == "variant":
                stats["variants"] += 1
            cur.execute(
                "UPDATE metadata SET cluster_key=?, cluster_role=?, primary_file_id=? "
                "WHERE file_id=?",
                (key, role, pfid, m["file_id"]),
            )
    conn.commit()
    print(
        f"dedupe: {stats['books']} books → {stats['clusters']} clusters "
        f"({stats['variants']} variants, {time.time()-t0:.1f}s)",
        file=sys.stderr,
    )
    return stats
