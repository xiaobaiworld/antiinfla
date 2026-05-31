# 整理书籍 — 进度与接续清单

> 这份文档是为了让下一个会话能直接从这里接续。  
> 最近更新：2026-05-31，commit `da72199`

## 一句话现状

NAS 运行 `web-0.8.0`（http://192.168.1.44:8766/），功能完整：
- 首页每日精选（business/literature/humanities 优先，日期种子）
- 筛选：分类/二级/跨界/作者/年代/格式/拼音排序
- 在线阅读：**EPUB / PDF / TXT / DOCX / MOBI / AZW3** 全部支持
- **用户系统**：匿名 UUID，阅读进度自动保存/恢复，评分/笔记/书签
- **书籍上传**：拖拽上传，SHA256 去重，自动入库
- **相关书推荐**：同 category2 + LLM fine_tags Jaccard

---

## 已完成功能总览

| 版本 | 功能 |
|------|------|
| web-0.6.0 | 拼音排序、跨界相关、出版年代、作者筛选、首页每日精选 |
| web-0.7.1 | 多格式阅读器（EPUB/PDF/TXT/DOCX/MOBI/AZW3）+ cover bug fix |
| web-0.8.0 | 用户系统 + 阅读进度 + 上传 + 相关书推荐 |

---

## 部署事实（权威）

| 项 | 值 |
|---|---|
| SSH | `ssh nas`（`bai@192.168.1.44:10022`，密钥 `~/.ssh/id_ed25519`） |
| 机器 | 绿联 DX4600，Linux x86_64，Docker 26.1.0 |
| compose 项目 | `/volume1/docker/books_organizer/src/`（项目名 `src`） |
| 当前容器 | `books_web` = `books_organizer:web-0.8.0`，端口 8766，healthy |
| 数据 | `src/data/books.db`（114M）+ `src/data/covers/`（49058 张） |
| 用户数据 | `src/data/user_data.db`（新建，首次访问自动创建） |
| 上传目录 | `src/data/uploads/`（容器内 `/data/uploads`，可写） |
| 书源 | external volume `books_share` → CIFS `//192.168.1.36/book`（`/books:ro`） |

### 同步代码到 NAS 的标准流程（每次 commit 后执行）

```bash
# 1. 同步源码
tar czf - -C books_organizer --exclude=__pycache__ --exclude='*.pyc' . | \
  ssh nas 'cat > /tmp/books_organizer.tar.gz && \
    cd /volume1/docker/books_organizer/src/books_organizer && tar xzf /tmp/books_organizer.tar.gz'

# 2. 构建新 tag（版本号递增）
ssh nas 'cd /volume1/docker/books_organizer/src && \
  docker build -f Dockerfile.web -t books_organizer:web-0.x.x . 2>&1 | tail -5'

# 3. 切换
ssh nas 'cd /volume1/docker/books_organizer/src && \
  TAG=web-0.x.x HOST_PORT=8766 docker compose up -d web'
```

**规则：commit 了就同步，不攒。已 commit = 已部署。**

---

## 用户系统架构（已实现）

### 数据库：`user_data.db`（独立，不混进 books.db）

- `users`：UUID + 显示名 + 合并关系
- `user_aliases`：合并后的旧 UUID → 主 UUID 映射
- `reading_history`：每本书的阅读进度（UNIQUE on user_id+book_id）
- `bookmarks`：书签（位置 + 标签）
- `notes`：笔记（支持增删改）
- `ratings`：5 星评分

### 前端用户流程
1. 首次访问 → `POST /api/user/init` 获取 UUID → 存 localStorage `books_uid`
2. 阅读器翻页/滚动 → 节流 5s → `POST /api/user/:id/history`
3. 再次打开阅读器 → 从 history 恢复上次位置
4. 首页"继续阅读"：最近 6 本未完成的书（进度 < 95%）

### API 端点（已实现）
```
POST /api/user/init            # 建/更新用户
GET  /api/user/:id             # 获取 profile
PUT  /api/user/:id/name        # 改显示名
POST /api/user/:id/merge       # 合并另一个 UUID

POST /api/user/:id/history     # 记录阅读进度
GET  /api/user/:id/history     # 阅读历史列表
GET  /api/user/:id/history/:book_id  # 某本书进度（恢复用）

POST /api/user/:id/bookmark    # 添加书签
GET  /api/user/:id/bookmarks/:book_id
DELETE /api/user/:id/bookmark/:bm_id

POST /api/user/:id/note        # 添加/更新笔记
GET  /api/user/:id/notes/:book_id
DELETE /api/user/:id/note/:note_id

POST /api/user/:id/rating      # 评分（1-5星）
GET  /api/user/:id/export      # 导出全部数据（JSON）
POST /api/user/:id/import      # 导入（合并模式）

POST /api/upload               # 书籍上传（multipart，200MB 限制）
GET  /api/book/:id/related     # 相关书（5 分钟缓存）
```

---

## 书籍上传（已实现）

- `POST /api/upload` — multipart，接收文件，SHA256 去重
- 上传目录：`BOOKS_UPLOAD_DIR`（默认 `BOOKS_ROOT/_上传`，docker 里设为 `/data/uploads`）
- rel_path 相对 `BOOKS_ROOT` 存储（若 UPLOAD_DIR 在 ROOT 下）或绝对路径
- 直接插入 `books.db`（source="upload"，confidence=0.5），立即在书库可见
- 前端：header "⬆ 上传" 按钮 → 拖拽/选文件 modal → 进度条 → 自动跳转详情页

### NAS 上传目录配置（当前：/data/uploads）
- 当前设置：上传到 `/data/uploads`（在 `./data:/data` 可写 volume 内）
- 若想让 `scan --incremental` 自动扫到：
  - 选项 A：改 BOOKS_UPLOAD_DIR 为 `/books/_上传`，同时把 `/books` 从 `:ro` 改为 `:rw`
  - 选项 B：手动在 pipeline 容器运行 `scan --incremental` + 指定 upload 目录

---

## 相关书推荐（已实现）

- API：`GET /api/book/:id/related` → `{"related": [{id,title,author,ext}, ...]}`
- 算法：
  1. 同 `category2`，按置信度降序取前 10
  2. `fine_tags` Jaccard 相似度（Jaccard > 0 才入选），扫 2000 条，取前 15
  3. 合并去重，最多返回 10 本
- 缓存：内存 5 分钟
- 展示：书籍详情页"相关书籍"横向滚动卡片
- llm-tag 覆盖率目前 2%（770/39751），相关书效果取决于标注量

---

## 关键路径

| 路径 | 用途 |
|------|------|
| `books_organizer/web.py` | **主源码**，所有 web 功能 |
| `books_organizer/user_db.py` | 用户数据库 schema + resolve_user |
| `books_organizer/paths.py` | 所有路径配置（含 USER_DB_PATH, UPLOAD_DIR） |
| `books_organizer/llm_tag.py` | LLM 标签生成（770 本已标注） |
| `.claude/worktrees/affectionate-roentgen-787453/books_organizer/books.db` | 当前唯一书库数据库（39751 本） |
| `.claude/worktrees/affectionate-roentgen-787453/.venv/` | Python 环境 |
| `books_organizer-docker/` | Dockerfile.web / compose / Makefile |

---

## 下一步（待做）

1. **llm-tag 全量**（后台慢跑）— 提升相关书推荐效果
   ```bash
   # 在 NAS pipeline 容器跑
   ssh nas 'docker run --rm -e BOOKS_DATA_DIR=/data -e ANTHROPIC_API_KEY=... \
     -v /volume1/docker/books_organizer/src/data:/data \
     books_organizer:latest python -m books_organizer llm-tag --concurrency 4'
   ```

2. **阅读器书签按钮** — 在 EPUB/TXT 阅读器里直接点击添加书签（当前只能从书籍详情页查看/删除）

3. **评分聚合展示** — 书籍详情页显示"所有用户平均分"（需要聚合 ratings 表）

4. **上传后 pipeline** — 上传的书自动触发 extract（需要 pipeline 容器）

---

## 残留问题

1. `~/Library/LaunchAgents/com.bai.books_sync.plist` 里引用不存在的脚本，建议 `rm -f` 清掉
2. `.claude/worktrees/affectionate-roentgen-787453/` 是旧 worktree，目前仍在用（.venv 和 books.db 在里面）
3. llm-tag 仅覆盖 2%，相关书推荐效果有限，需要跑全量
