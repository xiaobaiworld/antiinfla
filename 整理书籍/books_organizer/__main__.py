"""命令入口：python3 -m books_organizer <subcmd> ..."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import db, scan as scan_mod, report as report_mod

from .paths import BOOKS_ROOT as DEFAULT_ROOT, DB_PATH as DEFAULT_DB, ORGANIZED_DIR as DEFAULT_ORGANIZED


def cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    if not root.exists():
        print(f"error: root not found: {root}", file=sys.stderr)
        return 2
    conn = db.connect(Path(args.db))
    db.init(conn)
    print(f"scan: root={root} db={args.db}", file=sys.stderr)
    t0 = time.time()
    extra_skip = {x.strip() for x in args.exclude.split(",") if x.strip()}
    stats = scan_mod.scan(conn, root, compute_fingerprint=args.fingerprint, extra_skip=extra_skip)
    dt = time.time() - t0
    print(
        f"done in {dt:.1f}s — seen={stats['seen']} new={stats['new']} "
        f"updated={stats['updated']} unchanged={stats['unchanged']} errors={stats['errors']}",
        file=sys.stderr,
    )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    conn = db.connect(Path(args.db))
    db.init(conn)
    text = report_mod.report(conn)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"report written to {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    from . import extract as extract_mod
    root = Path(args.root).resolve()
    conn = db.connect(Path(args.db))
    db.init(conn)
    exts = [e.strip().lower() for e in args.exts.split(",") if e.strip()]
    stats = extract_mod.extract_all(
        conn, root, exts=exts, limit=args.limit, force=args.force,
    )
    print(f"extract done — {stats}", file=sys.stderr)
    return 0


def cmd_lookup(args: argparse.Namespace) -> int:
    from . import lookup as lookup_mod
    conn = db.connect(Path(args.db))
    db.init(conn)
    stats = lookup_mod.lookup_all(conn, limit=args.limit, force=args.force)
    print(f"lookup done — {stats}", file=sys.stderr)
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    from . import organize as organize_mod
    conn = db.connect(Path(args.db))
    db.init(conn)
    stats = organize_mod.plan_all(conn, min_confidence=args.min_confidence, limit=args.limit)
    print(f"plan done — {stats}", file=sys.stderr)
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    from . import organize as organize_mod
    root = Path(args.root).resolve()
    organized = Path(args.organized).resolve()
    conn = db.connect(Path(args.db))
    db.init(conn)
    stats = organize_mod.apply_all(conn, root, organized_dir=organized)
    print(f"apply done — {stats}", file=sys.stderr)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """快速看进度。"""
    conn = db.connect(Path(args.db))
    db.init(conn)
    out = []
    files_total = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    out.append(f"files: {files_total}")
    for kind, n in conn.execute(
        "SELECT kind, COUNT(*) FROM files GROUP BY kind ORDER BY 2 DESC"
    ):
        out.append(f"  {kind}: {n}")
    meta_total = conn.execute("SELECT COUNT(*) FROM metadata").fetchone()[0]
    out.append(f"metadata: {meta_total}")
    for src, n in conn.execute(
        "SELECT source, COUNT(*) FROM metadata GROUP BY source ORDER BY 2 DESC"
    ):
        out.append(f"  {src}: {n}")
    lookups = conn.execute("SELECT COUNT(*) FROM lookups").fetchone()[0]
    out.append(f"lookups (cached): {lookups}")
    plans = conn.execute("SELECT COUNT(*) FROM plan").fetchone()[0]
    applied = conn.execute("SELECT COUNT(*) FROM plan WHERE applied_at IS NOT NULL").fetchone()[0]
    out.append(f"plans: {plans} ({applied} applied)")
    print("\n".join(out))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="books_organizer")
    p.add_argument("--db", default=str(DEFAULT_DB))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="阶段 1：扫盘建库")
    s.add_argument("--root", default=str(DEFAULT_ROOT))
    s.add_argument("--fingerprint", action="store_true")
    s.add_argument("--exclude", default="",
                   help="逗号分隔的子目录名（精确匹配），整体跳过")
    s.set_defaults(func=cmd_scan)

    r = sub.add_parser("report", help="输出扫盘报告")
    r.add_argument("--out")
    r.set_defaults(func=cmd_report)

    e = sub.add_parser("extract", help="阶段 2：本地元数据 + 内嵌封面")
    e.add_argument("--root", default=str(DEFAULT_ROOT))
    e.add_argument("--exts", default="epub,pdf",
                   help="逗号分隔扩展名，默认 epub,pdf")
    e.add_argument("--limit", type=int)
    e.add_argument("--force", action="store_true")
    e.set_defaults(func=cmd_extract)

    l = sub.add_parser("lookup", help="阶段 3：豆瓣 + Google Books 补元数据 + 封面")
    l.add_argument("--limit", type=int)
    l.add_argument("--force", action="store_true")
    l.set_defaults(func=cmd_lookup)

    pl = sub.add_parser("plan", help="阶段 4a：生成归档计划（dry-run）")
    pl.add_argument("--min-confidence", type=float, default=0.6)
    pl.add_argument("--limit", type=int)
    pl.set_defaults(func=cmd_plan)

    ap = sub.add_parser("apply", help="阶段 4b：建立硬链接（不动原文件）")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--organized", default=str(DEFAULT_ORGANIZED))
    ap.set_defaults(func=cmd_apply)

    st = sub.add_parser("status", help="看当前进度")
    st.set_defaults(func=cmd_status)

    w = sub.add_parser("web", help="启动在线阅读站")
    w.add_argument("--host", default="0.0.0.0")
    w.add_argument("--port", type=int, default=8765)
    w.set_defaults(func=cmd_web)

    d = sub.add_parser("dedupe", help="阶段 4：版本/重复聚类")
    d.set_defaults(func=cmd_dedupe)

    ri = sub.add_parser("reindex", help="补 title_sort(拼音排序键)和 pub_year(出版年代)")
    ri.add_argument("--force", action="store_true", help="全表重算,默认只补空值")
    ri.set_defaults(func=cmd_reindex)

    lt = sub.add_parser("llm-tag", help="阶段 5：LLM 细粒度标签 + 分类纠正")
    lt.add_argument("--db", default=str(DEFAULT_DB))
    lt.add_argument("--model", default=None, help="默认 claude-haiku-4-5")
    lt.add_argument("--limit", type=int, default=None, help="只处理前 N 本(试跑)")
    lt.add_argument("--batch-size", type=int, default=25)
    lt.add_argument("--concurrency", type=int, default=4)
    lt.add_argument("--dry-run", action="store_true", help="只打印 prompt,不调 API")
    lt.add_argument("--force", action="store_true", help="重标已标注过的书")
    lt.set_defaults(func=cmd_llm_tag)

    pp = sub.add_parser("pipeline", help="一键端到端：scan → extract → lookup → dedupe → plan → apply")
    pp.add_argument("--root", default=str(DEFAULT_ROOT))
    pp.add_argument("--organized", default=str(DEFAULT_ORGANIZED))
    pp.add_argument("--exclude", default="wechatbook,office 相关",
                    help="扫描时跳过这些子目录（逗号分隔）")
    pp.add_argument("--exts", default="epub,mobi,azw3,azw,pdf",
                    help="extract 阶段处理的扩展名（默认含 mobi/azw3，靠 calibre）")
    pp.add_argument("--lookup-limit", type=int, default=None,
                    help="lookup 阶段最多处理多少条")
    pp.add_argument("--skip-scan", action="store_true")
    pp.add_argument("--skip-extract", action="store_true")
    pp.add_argument("--skip-lookup", action="store_true")
    pp.add_argument("--skip-apply", action="store_true")
    pp.set_defaults(func=cmd_pipeline)

    return p


def cmd_dedupe(args: argparse.Namespace) -> int:
    from . import dedupe as dedupe_mod
    conn = db.connect(Path(args.db))
    db.init(conn)
    dedupe_mod.cluster_all(conn)
    return 0


def cmd_pipeline(args: argparse.Namespace) -> int:
    from . import pipeline as pipe
    exclude = {x.strip() for x in args.exclude.split(",") if x.strip()}
    exts = [e.strip().lower() for e in args.exts.split(",") if e.strip()]
    return pipe.run_pipeline(
        Path(args.db), Path(args.root).resolve(), Path(args.organized).resolve(),
        exclude_dirs=exclude, extract_exts=exts, lookup_limit=args.lookup_limit,
        skip_scan=args.skip_scan, skip_extract=args.skip_extract,
        skip_lookup=args.skip_lookup, skip_apply=args.skip_apply,
    )


def cmd_web(args: argparse.Namespace) -> int:
    from . import web as web_mod
    web_mod.run(host=args.host, port=args.port)
    return 0


def cmd_reindex(args: argparse.Namespace) -> int:
    from . import index_fields
    conn = db.connect(Path(args.db))
    db.init(conn)
    stats = index_fields.reindex(conn, force=args.force)
    print(f"reindex done — {stats}", file=sys.stderr)
    return 0


def cmd_llm_tag(args: argparse.Namespace) -> int:
    from . import llm_tag
    conn = db.connect(Path(args.db))
    db.init(conn)
    stats = llm_tag.run(
        conn,
        model=args.model or llm_tag.DEFAULT_MODEL,
        limit=args.limit,
        batch_size=args.batch_size,
        concurrency=args.concurrency,
        dry_run=args.dry_run,
        force=args.force,
    )
    return 1 if stats.get("error") else 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
