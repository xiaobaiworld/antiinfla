"""用户数据库 — 匿名 UUID + 阅读历史/书签/笔记/评分。"""
from __future__ import annotations

import sqlite3
import time

from .paths import USER_DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  name TEXT,
  merged_into TEXT,
  created_at REAL,
  last_seen REAL
);
CREATE TABLE IF NOT EXISTS user_aliases (
  alias_id TEXT PRIMARY KEY,
  primary_id TEXT,
  merged_at REAL
);
CREATE TABLE IF NOT EXISTS reading_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  book_id INTEGER,
  started_at REAL,
  last_read_at REAL,
  progress_pct REAL DEFAULT 0,
  last_position TEXT,
  total_time_sec INTEGER DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_history_user_book ON reading_history(user_id, book_id);
CREATE INDEX IF NOT EXISTS idx_history_user_time ON reading_history(user_id, last_read_at);
CREATE TABLE IF NOT EXISTS bookmarks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  book_id INTEGER,
  position TEXT,
  label TEXT,
  created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_bm_user_book ON bookmarks(user_id, book_id);
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  book_id INTEGER,
  position TEXT,
  text TEXT,
  created_at REAL,
  updated_at REAL
);
CREATE INDEX IF NOT EXISTS idx_notes_user_book ON notes(user_id, book_id);
CREATE TABLE IF NOT EXISTS ratings (
  user_id TEXT,
  book_id INTEGER,
  rating INTEGER,
  review TEXT,
  created_at REAL,
  PRIMARY KEY(user_id, book_id)
);
"""


def get_user_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(USER_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def resolve_user(conn: sqlite3.Connection, user_id: str) -> str:
    """Follow alias chain to canonical user_id (max 10 hops to prevent cycles)."""
    seen: set[str] = set()
    for _ in range(10):
        if user_id in seen:
            break
        seen.add(user_id)
        row = conn.execute(
            "SELECT primary_id FROM user_aliases WHERE alias_id=?", (user_id,)
        ).fetchone()
        if row:
            user_id = row["primary_id"]
        else:
            break
    return user_id
