"""docker-demo: validate deployment chain before dockerizing books_organizer."""
from __future__ import annotations

import os
import platform
import sqlite3
from pathlib import Path

from flask import Flask, jsonify

app = Flask(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
MOUNT_DIR = Path(os.environ.get("MOUNT_DIR", "/tmp"))
DB_PATH = DATA_DIR / "counter.db"


def _db() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS counter (id INTEGER PRIMARY KEY, n INTEGER NOT NULL)")
    conn.execute("INSERT OR IGNORE INTO counter (id, n) VALUES (1, 0)")
    conn.commit()
    return conn


@app.route("/health")
def health():
    return jsonify({
        "ok": True,
        "arch": platform.machine(),
        "platform": platform.platform(),
        "data_dir_exists": DATA_DIR.exists(),
        "mount_dir_exists": MOUNT_DIR.exists(),
    })


@app.route("/count")
def count():
    conn = _db()
    conn.execute("UPDATE counter SET n = n + 1 WHERE id = 1")
    conn.commit()
    n = conn.execute("SELECT n FROM counter WHERE id = 1").fetchone()[0]
    conn.close()
    return jsonify({"n": n, "db_path": str(DB_PATH)})


@app.route("/")
def index():
    if not MOUNT_DIR.exists():
        return jsonify({"error": f"mount dir not found: {MOUNT_DIR}"}), 500
    entries = []
    for p in sorted(MOUNT_DIR.iterdir())[:50]:
        entries.append({"name": p.name, "is_dir": p.is_dir(),
                        "size": p.stat().st_size if p.is_file() else None})
    return jsonify({"mount": str(MOUNT_DIR), "count": len(entries), "entries": entries})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8765, debug=False)
