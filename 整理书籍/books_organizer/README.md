# books_organizer

NAS `/Volumes/book`（3.6TB，几十万文件）的书籍整理流水线 + 在线阅读站。

## 整夜在跑

启动了两个长跑后台任务：

1. **pipeline** — `scan → extract → lookup → plan → apply`
   - 扫 `/Volumes/book`（已排除 `wechatbook`，那是微信文章存档）
   - 抽 EPUB / PDF 内嵌元数据 + 封面
   - 通过豆瓣 / Google Books 补元数据 + 封面 + 简介（限 5000 本，限流 2.5s/req）
   - 在 `/Volumes/book/_整理后/` 生成符号链接树（SMB 不支持硬链接，自动回退到 symlink，效果一样）
   - 日志：`books_organizer/pipeline.log`

2. **web reader** — Flask，端口 8765
   - 本机：http://localhost:8765
   - 局域网：http://192.168.1.110:8765
   - 边跑边看，pipeline 处理完一批就出现在页面上（刷新即可）

## 在浏览器看

http://192.168.1.110:8765

- 首页：封面网格，支持按格式 / 排序筛选 + 搜索
- 点封面进详情页：豆瓣简介、出版信息、文件信息
- EPUB / PDF 都能直接在浏览器里读（用 epub.js / pdf.js）

## 整理后的目录结构

在 `/Volumes/book/_整理后/`（symlink，**原文件不动**）：

```
_整理后/
├── by-author/{首字母}/{作者}/{书名}.ext
├── by-category/{分类}/{书名} - {作者}.ext
└── by-title/{首字}/{书名} - {作者}.ext
```

不喜欢这个布局可以直接 `rm -rf /Volumes/book/_整理后/`，重跑 `plan + apply`，原文件不会动。

## 看进度

```bash
# 当前 DB 统计
.venv/bin/python3 -m books_organizer status

# pipeline 实时日志
tail -f books_organizer/pipeline.log
```

## 阶段说明

| 阶段 | 命令 | 改文件？ | 说明 |
|---|---|---|---|
| 1 | `scan` | 否 | 走遍目录，记录所有文件 size/mtime；断点续跑 |
| 2 | `extract` | 否 | EPUB（ebooklib）/PDF（pypdf）抽嵌入元数据 + 封面 |
| 3 | `lookup` | 否 | 豆瓣 + Google Books 在线补全；缓存到 SQLite；限流 |
| 4a | `plan` | 否 | 生成归档计划（dry-run）；落 `plan` 表 |
| 4b | `apply` | **是** | 按 plan 建 symlink/硬链接；原文件不动 |
| 5 | `web` | 否 | Flask 阅读站 |

每个阶段都可以独立、重复跑。

## 单步排错

```bash
# 只扫某子目录
.venv/bin/python3 -m books_organizer scan --root "/Volumes/book/ForBoox"

# 强制重抓某本的元数据
.venv/bin/python3 -m books_organizer extract --exts epub --force

# 重新生成归档计划
.venv/bin/python3 -m books_organizer plan --min-confidence 0.7

# 端到端 pipeline（带断点续跑）
.venv/bin/python3 -m books_organizer pipeline --exclude wechatbook --exts epub,pdf
```

## 数据库

`books_organizer/books.db`（SQLite，WAL 模式）

四张表：

- `files` — 全部扫到的文件清单
- `metadata` — 抽出的书目元数据
- `lookups` — 豆瓣 / Google Books 缓存
- `plan` — 归档计划（applied_at IS NULL 表示未执行）

```bash
.venv/bin/python3 -c "
import sqlite3
c=sqlite3.connect('books_organizer/books.db')
for r in c.execute('SELECT title, author, confidence FROM metadata WHERE title IS NOT NULL LIMIT 10'):
    print(r)
"
```

## 已知 / 待办

- [ ] MOBI / AZW3 暂时不抽（Python 纯解析较弱），晚点装 calibre 走 `ebook-meta` 兜底
- [ ] 扫描版 PDF 没有 OCR，只能从文件名推断；可后接 OCR 阶段
- [ ] 现在跑的是前 5000 本的 lookup；剩下的可以早晨再启一次 `lookup`，断点续跑
- [ ] WeChat 公众号文章目录（`wechatbook/`）目前完全跳过；要做的话单独写一个 wechat 整理流程

## 项目结构

```
books_organizer/
├── __init__.py
├── __main__.py     CLI 入口
├── db.py           SQLite 连接 + 初始化
├── schema.sql      表结构
├── scan.py         阶段 1
├── extract.py      阶段 2
├── lookup.py       阶段 3
├── organize.py     阶段 4
├── pipeline.py     端到端编排
├── web.py          阶段 5（Flask）
├── books.db        SQLite 数据库（不入 git）
├── covers/         封面缓存（不入 git）
└── pipeline.log    pipeline 日志
```
