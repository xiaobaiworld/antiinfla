# books_organizer Docker 化工作区

这是把 `books_organizer/` 打包成镜像部署到目标 NAS（绿联云）的所有非源码资产。

源码已经合并到本仓的 `整理书籍/books_organizer/`。

## 文件清单

| 文件 | 作用 |
|---|---|
| `REFACTOR-PLAN.md` | 7 文件改造点 diff（env 化硬编码路径），照单执行 |
| `Dockerfile` | python:3.11-slim-bookworm + calibre + 包，pipeline 全功能镜像 |
| `Dockerfile.web` | 仅 web 子集（不要 calibre），更小、启动更快 |
| `docker-compose.yml` | `web` 常驻 + `pipeline` 按需触发 |
| `requirements.txt` | 5 个直接依赖 |
| `Makefile` | build / save / scp / deploy / migrate-db / rollback |
| `.dockerignore` | 排除 venv、DB、covers、log |

## 执行顺序

**前置**：`../docker-demo/` 的 8 步验收必须全过（证明部署链路本身通）。

1. **改源码**（按 REFACTOR-PLAN.md 7 个文件）—— Mac 上验 `python -m books_organizer status` 不变
2. **本地容器化验证**：`make local-test` —— Mac docker 起 web 容器，浏览器看 35k 本书
3. **数据迁移**：`make migrate-db NAS=...` —— stop Mac pipeline/web，checkpoint WAL，rsync 到 NAS
4. **NAS 部署**：`make deploy NAS=... NAS_DIR=...`
5. **接管**：`curl http://NAS_IP:8765/api/facets` 看到一致数据，停 Mac 上的 web
6. **lookup 决策**：lookup 阶段留在 Mac 上跑（用户已确认绿联出墙不通），跑完 rsync DB 到 NAS

## 已知遗留

- pipeline 在 NAS 上跑时，源 NAS 通过 SMB/NFS 挂在目标 NAS 本地 → 容器 bind mount。**extract 性能会比 Mac 慢**（cifs.ko 不如 macOS native）。先量出真实速度再考虑是否把 pipeline 也留在 Mac。
- `_整理后/` symlink 树会建在源 NAS 的 SMB 卷上 → 链接路径是源 NAS 视角，不是容器视角。需在 4.1 改造里把 `organize.py` 的 link 目标改成相对路径，否则 link 在 Mac/NAS 之间不通用。**这一条暂未列入 REFACTOR-PLAN，验证时再决定**。
- calibre Linux 版本可能跟 Mac 不一致 → 输出 label 翻译问题。`LC_ALL=C` 兜底，但要在 step 2 真测一下 mobi 抽元数据是否成功。
