"""SQLite 连接与初始化。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=60.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=60000")
    conn.row_factory = sqlite3.Row
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    # 幂等迁移：旧 DB 加上去重相关列
    cols = {r[1] for r in conn.execute("PRAGMA table_info(metadata)")}
    if "cluster_key" not in cols:
        conn.execute("ALTER TABLE metadata ADD COLUMN cluster_key TEXT")
    if "cluster_role" not in cols:
        conn.execute("ALTER TABLE metadata ADD COLUMN cluster_role TEXT NOT NULL DEFAULT 'primary'")
    if "primary_file_id" not in cols:
        conn.execute("ALTER TABLE metadata ADD COLUMN primary_file_id INTEGER")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_meta_cluster ON metadata(cluster_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_meta_primary ON metadata(primary_file_id)")
    conn.commit()
