"""阶段 1 后的全景报告：扩展名分布、目录分布、可疑文件、估算体积。"""
from __future__ import annotations

import sqlite3


def human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def report(conn: sqlite3.Connection) -> str:
    out: list[str] = []
    cur = conn.cursor()

    total, total_size = cur.execute(
        "SELECT COUNT(*), COALESCE(SUM(size), 0) FROM files"
    ).fetchone()
    out.append(f"# 扫盘报告")
    out.append("")
    out.append(f"总文件数：{total}    总体积：{human_bytes(total_size)}")
    out.append("")

    out.append("## 按 kind 分布")
    out.append("")
    out.append("| kind | 文件数 | 体积 |")
    out.append("|---|---:|---:|")
    for row in cur.execute(
        "SELECT kind, COUNT(*) n, COALESCE(SUM(size),0) s FROM files GROUP BY kind ORDER BY n DESC"
    ):
        out.append(f"| {row['kind']} | {row['n']} | {human_bytes(row['s'])} |")
    out.append("")

    out.append("## 按扩展名分布（top 20）")
    out.append("")
    out.append("| ext | 文件数 | 体积 |")
    out.append("|---|---:|---:|")
    for row in cur.execute(
        "SELECT ext, COUNT(*) n, COALESCE(SUM(size),0) s FROM files "
        "GROUP BY ext ORDER BY n DESC LIMIT 20"
    ):
        out.append(f"| {row['ext'] or '(无)'} | {row['n']} | {human_bytes(row['s'])} |")
    out.append("")

    out.append("## 顶层目录分布（top 30）")
    out.append("")
    out.append("| 目录 | 文件数 | 体积 |")
    out.append("|---|---:|---:|")
    rows = cur.execute(
        """
        SELECT
          CASE WHEN instr(rel_path, '/') > 0
               THEN substr(rel_path, 1, instr(rel_path, '/')-1)
               ELSE '(根)' END AS top,
          COUNT(*) AS n,
          COALESCE(SUM(size),0) AS s
        FROM files
        GROUP BY top
        ORDER BY n DESC
        LIMIT 30
        """
    ).fetchall()
    for row in rows:
        out.append(f"| {row['top']} | {row['n']} | {human_bytes(row['s'])} |")
    out.append("")

    out.append("## 可疑文件")
    out.append("")
    zero = cur.execute("SELECT COUNT(*) FROM files WHERE size = 0").fetchone()[0]
    huge = cur.execute("SELECT COUNT(*) FROM files WHERE size > 1024*1024*1024").fetchone()[0]
    no_ext = cur.execute("SELECT COUNT(*) FROM files WHERE ext = ''").fetchone()[0]
    out.append(f"- 零字节文件：{zero}")
    out.append(f"- 超大文件（>1GB）：{huge}")
    out.append(f"- 无扩展名：{no_ext}")
    out.append("")

    out.append("## 快指纹重复（同 fingerprint 出现 ≥2 次）")
    out.append("")
    dup = cur.execute(
        """
        SELECT fingerprint, COUNT(*) AS n, COALESCE(SUM(size),0) AS s
        FROM files
        WHERE fingerprint != '' AND kind != 'other'
        GROUP BY fingerprint
        HAVING n >= 2
        """
    ).fetchall()
    dup_files = sum(r["n"] for r in dup)
    dup_groups = len(dup)
    dup_waste = sum((r["n"] - 1) * (r["s"] / r["n"]) for r in dup if r["n"] > 0)
    out.append(f"- 重复组数：{dup_groups}")
    out.append(f"- 涉及文件：{dup_files}")
    out.append(f"- 预计去重可省：{human_bytes(int(dup_waste))}")
    out.append("")

    return "\n".join(out)
