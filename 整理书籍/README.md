# 整理书籍

把一台 Mac 上 35k+ 本书的书库(`/Volumes/book`)做扫描、抽元数据、去重、分类、补全(豆瓣/Google Books)、生成在线阅读站,并最终容器化部署到绿联 NAS。

## 目录结构

| 目录 | 作用 |
|---|---|
| `books_organizer/` | 主源码包 — pipeline + web,通过 `python -m books_organizer ...` 调用 |
| `books_organizer-docker/` | 把 `books_organizer/` 容器化的资产(Dockerfile / compose / Makefile) |
| `docker-demo/` | 一次性的部署链路验证项目;走通后即可删除 |

## 本地开发

```bash
cd /Users/bai/code/整理书籍
python3 -m venv .venv
.venv/bin/pip install -r books_organizer-docker/requirements.txt
.venv/bin/python -m books_organizer status
.venv/bin/python -m books_organizer web --port 8765
```

数据库 `books.db` 不在 git 跟踪范围,需要从其他地方拷贝或重新跑 pipeline 生成。

## 部署链路

`docker-demo/docs/CHECKLIST.md` 8 步过完 → `books_organizer-docker/Makefile` 的 `local-test` → `migrate-db` → `deploy`。
