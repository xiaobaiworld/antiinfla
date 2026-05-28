# books_organizer 代码改造清单（env 化路径）

**目的**：把硬编码 macOS 路径替换为环境变量，使同一份代码能在 Mac 本地、Docker 容器里都跑。

**前置**：docker-demo/ 的 8 步验收先全过；本文件改动等那之后才执行。

**安全**：所有改动都是"加 env 默认值 = 原值"，本地行为不变；容器里通过 env 覆盖。

**状态**：✅ 已全部执行完成（见 `整理书籍/books_organizer/paths.py` 与 5 个改造文件）。本文件保留作历史记录。

---

## 0. 共享辅助（新建文件）

新建 `books_organizer/paths.py`：

```python
"""集中处理所有路径配置。任何模块拿默认路径都从这里来，不直接写常量。"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    v = os.environ.get(name)
    return Path(v) if v else default


_PKG_DIR = Path(__file__).resolve().parent

# 书源：扫描和阅读的根目录
BOOKS_ROOT = _env_path("BOOKS_ROOT", Path("/Volumes/book"))

# 数据目录：放 books.db, covers/, logs/
BOOKS_DATA_DIR = _env_path("BOOKS_DATA_DIR", _PKG_DIR)

# 派生路径
DB_PATH = _env_path("BOOKS_DB", BOOKS_DATA_DIR / "books.db")
COVER_DIR = _env_path("BOOKS_COVERS", BOOKS_DATA_DIR / "covers")
LOG_FILE = _env_path("BOOKS_LOG", BOOKS_DATA_DIR / "pipeline.log")
ORGANIZED_DIR = _env_path("BOOKS_ORGANIZED", BOOKS_ROOT / "_整理后")

# calibre 二进制：Mac 在 /Applications/...，Linux 容器在 PATH 里有 ebook-meta
CALIBRE_EBOOK_META = os.environ.get(
    "CALIBRE_EBOOK_META",
    "/Applications/calibre.app/Contents/MacOS/ebook-meta",
)
if not Path(CALIBRE_EBOOK_META).exists():
    # 退化到 PATH 查找（容器里 apt install calibre 后会有）
    fallback = shutil.which("ebook-meta")
    if fallback:
        CALIBRE_EBOOK_META = fallback

HAS_CALIBRE = Path(CALIBRE_EBOOK_META).exists()
```

---

## 1. `extract.py` 改 3 处

**Line 34**:
```diff
-COVER_DIR = Path(__file__).parent / "covers"
+from .paths import COVER_DIR, CALIBRE_EBOOK_META, HAS_CALIBRE
```

**Line 36-37**: 删除（移到 paths.py）
```diff
-CALIBRE_EBOOK_META = "/Applications/calibre.app/Contents/MacOS/ebook-meta"
-HAS_CALIBRE = Path(CALIBRE_EBOOK_META).exists()
```

无其他改动；line 272/280 用的就是 `COVER_DIR` 变量，import 后自动正确。

---

## 2. `web.py` 改 2 处

**Line 19-22**:
```diff
-from .extract import COVER_DIR
-
-ROOT = Path("/Volumes/book")
-DB_PATH = Path(__file__).parent / "books.db"
+from .paths import BOOKS_ROOT as ROOT, DB_PATH, COVER_DIR
```

其余引用 (`ROOT / rel_path`, `COVER_DIR / ...`, `sqlite3.connect(DB_PATH)`) 不变。

---

## 3. `lookup.py` 改 1 处

**Line 22**:
```diff
-from .extract import COVER_DIR
+from .paths import COVER_DIR
```

---

## 4. `pipeline.py` 改 3 处

**Line 17-19**:
```diff
-DEFAULT_ROOT = Path("/Volumes/book")
-DEFAULT_ORGANIZED = DEFAULT_ROOT / "_整理后"
-LOG_FILE = Path(__file__).parent / "pipeline.log"
+from .paths import BOOKS_ROOT as DEFAULT_ROOT, ORGANIZED_DIR as DEFAULT_ORGANIZED, LOG_FILE
```

---

## 5. `__main__.py` 改 1 处

**Line 11-13**:
```diff
-DEFAULT_ROOT = Path("/Volumes/book")
-DEFAULT_DB = Path(__file__).parent / "books.db"
-DEFAULT_ORGANIZED = DEFAULT_ROOT / "_整理后"
+from .paths import BOOKS_ROOT as DEFAULT_ROOT, DB_PATH as DEFAULT_DB, ORGANIZED_DIR as DEFAULT_ORGANIZED
```

---

## 6. 本地验证（Mac，改完后必须过）

```bash
cd /Users/bai/code/整理书籍

# 不设 env：行为应与改造前完全一致
.venv/bin/python3 -m books_organizer status
# 期望：files=201981, metadata=35105+, lookups=0, plans=15

# 设 env：把数据目录改到 /tmp 试一遍
BOOKS_DATA_DIR=/tmp/bo-test-data \
BOOKS_ROOT=/Volumes/book \
.venv/bin/python3 -m books_organizer status
# 期望：报错 "no such table" 或类似（因为新位置没 DB），证明 env 生效

# 启 web 验本地不变
.venv/bin/python3 -m books_organizer web --port 8766
# 浏览器开 http://localhost:8766，能看到 35k 本书
```

7 个文件总改动：新增 1 + 修改 5（每个 1-3 行）。

---

## 7. Docker 镜像里的环境变量

```yaml
# docker-compose.yml 片段
environment:
  BOOKS_ROOT: /books              # 容器内书源挂载点
  BOOKS_DATA_DIR: /data           # 容器内数据卷挂载点
  LANG: C.UTF-8
  LC_ALL: C                       # 强制 calibre 英文输出，正则才不会失配
  PYTHONUNBUFFERED: 1
```
