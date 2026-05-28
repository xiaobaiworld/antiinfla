"""集中路径配置。所有模块默认从这里取路径，可被环境变量覆盖。"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    v = os.environ.get(name)
    return Path(v) if v else default


_PKG_DIR = Path(__file__).resolve().parent

BOOKS_ROOT = _env_path("BOOKS_ROOT", Path("/Volumes/book"))
BOOKS_DATA_DIR = _env_path("BOOKS_DATA_DIR", _PKG_DIR)

DB_PATH = _env_path("BOOKS_DB", BOOKS_DATA_DIR / "books.db")
COVER_DIR = _env_path("BOOKS_COVERS", BOOKS_DATA_DIR / "covers")
LOG_FILE = _env_path("BOOKS_LOG", BOOKS_DATA_DIR / "pipeline.log")
ORGANIZED_DIR = _env_path("BOOKS_ORGANIZED", BOOKS_ROOT / "_整理后")

CALIBRE_EBOOK_META = os.environ.get(
    "CALIBRE_EBOOK_META",
    "/Applications/calibre.app/Contents/MacOS/ebook-meta",
)
if not Path(CALIBRE_EBOOK_META).exists():
    fallback = shutil.which("ebook-meta")
    if fallback:
        CALIBRE_EBOOK_META = fallback

HAS_CALIBRE = Path(CALIBRE_EBOOK_META).exists()
