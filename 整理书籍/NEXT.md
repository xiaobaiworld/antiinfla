# 整理书籍 — 进度与接续清单

> 最近更新：2026-06-01，commit `f718e04`（web-0.9.0）

## 一句话现状

NAS 运行 `web-0.9.0`（http://192.168.1.44:8766/），书库 39751 本，功能完整。

---

## 已完成功能总览

| 版本 | 功能 |
|------|------|
| web-0.6.0 | 拼音排序、跨界相关、出版年代、作者筛选、首页每日精选 |
| web-0.7.1 | 多格式阅读器（EPUB/PDF/TXT/DOCX/MOBI/AZW3）+ 封面 bug fix |
| web-0.8.0 | 用户系统（UUID）+ 阅读进度 + 书籍上传 + 相关书推荐 |
| web-0.8.1 | 用户侧边栏改进：合并前预览对方阅读历史 |
| web-0.8.2 | 首页"换一批"精选 + 🎲 随机推荐 + 阅读器返回首页 |
| web-0.8.3 | 阅读器内 📝 笔记面板（EPUB/TXT/DOCX/MOBI） |
| web-0.8.4 | `/shelf` 我的书架页（进度全览、筛选阅读中/已读完） |
| web-0.8.5 | 阅读器内 🔖 彩色书签面板（EPUB/TXT/MOBI），可跳转 |
| web-0.8.6 | 详情页书签彩色圆点 + 阅读器 ☰ 目录面板（EPUB/MOBI 真实目录，TXT 章节扫描，DOCX 标题扫描） |
| web-0.8.7 | 修复 EPUB/MOBI 进度始终为 0 的 bug（补 `book.locations.generate(1024)`） |
| web-0.8.8 | EPUB/MOBI 阅读器：页码显示 N/M 页 + 右侧可拖动垂直进度条 |
| web-0.8.9 | 阅读器 toolbar 重排：目录移至左侧、详情按钮化、进度条改为 header 内水平内联 |
| web-0.9.0 | `/admin` 管理后台（多书源增删/触发扫描/概况面板）+ 全站移动端响应式适配 |

---

## 部署事实（权威）

| 项 | 值 |
|---|---|
| SSH | `ssh nas`（`bai@192.168.1.44:10022`，密钥 `~/.ssh/id_ed25519`） |
| 机器 | 绿联 DX4600，Linux x86_64，Docker 26.1.0 |
| compose 项目 | `/volume1/docker/books_organizer/src/`（项目名 `src`） |
| 当前容器 | `books_web` = `books_organizer:web-0.8.8`，端口 8766 |
| 数据 | `src/data/books.db`（114M，39751 本） |
| 用户数据 | `src/data/user_data.db`（自动创建） |
| 上传目录 | `src/data/uploads/`（容器内 `/data/uploads`） |
| 书源 | external volume `books_share` → CIFS `/books:ro` |
| 书源 SMB | `smb://admin@192.168.1.36/book`（admin 密码另存） |

### 同步 + 部署标准流程

```bash
# 1. 同步源码（从整理书籍/目录运行）
tar czf - -C /Users/bai/code/整理书籍 --exclude=__pycache__ --exclude='*.pyc' books_organizer | \
  ssh nas 'cat > /tmp/books_organizer.tar.gz && \
    cd /volume1/docker/books_organizer/src && tar xzf /tmp/books_organizer.tar.gz'

# 2. 构建（版本号递增）
ssh nas 'cd /volume1/docker/books_organizer/src && \
  docker build -f Dockerfile.web -t books_organizer:web-0.X.X . 2>&1 | tail -5'

# 3. 切换（--pull never 防止去拉 Docker Hub）
ssh nas 'cd /volume1/docker/books_organizer/src && \
  TAG=web-0.X.X HOST_PORT=8766 docker compose up -d --pull never web'
```

**规则：commit 了就同步，不攒。已 commit = 已部署。**

### 本地开发启动

```bash
# 书文件挂载（先挂，否则 EPUB/PDF 打开 404）
sudo mkdir -p /Volumes/book
mount_smbfs //admin@192.168.1.36/book /Volumes/book

# 启动服务
mkdir -p /tmp/books_uploads
BOOKS_DATA_DIR=.claude/worktrees/affectionate-roentgen-787453/books_organizer \
BOOKS_UPLOAD_DIR=/tmp/books_uploads \
.claude/worktrees/affectionate-roentgen-787453/.venv/bin/python \
  -m books_organizer web --port 8765

# 同步 NAS 历史数据到本地（可选）
scp nas:/volume1/docker/books_organizer/src/data/user_data.db \
  .claude/worktrees/affectionate-roentgen-787453/books_organizer/user_data.db
```

---

## 功能详解

### 用户系统（`user_data.db`）

**账号机制**
- 首次访问自动生成 UUID，存 `localStorage['books_uid']`，无需注册/登录
- 可设置显示名（纯标签）
- 支持多设备账号合并：输入另一个 UUID → 预览对方阅读历史 → 确认合并
- 数据导出（JSON）/ 导入（合并模式）
- 入口：首页 header 👤 图标 → 右侧侧边栏

**数据库表**（独立 `user_data.db`，不混进 `books.db`）

| 表 | 用途 |
|---|---|
| `users` | UUID + 显示名 + 合并关系 |
| `user_aliases` | 被合并的旧 UUID → 主 UUID |
| `reading_history` | 每本书的进度（UNIQUE on user_id+book_id） |
| `bookmarks` | 书签（位置 + 颜色 + 备注） |
| `notes` | 笔记（支持增删改） |
| `ratings` | 5 星评分 |

### 阅读进度

- EPUB/MOBI：`book.locations.generate(1024)` 后用字符数精确计算百分比，节流 5s POST
- TXT：滚动时记录 scrollTop/maxScroll 百分比，节流 5s POST
- 再次打开阅读器 → 自动跳到上次位置
- 书籍详情页：显示进度条 + "继续阅读 XX%"按钮
- 首页：最近 6 本未读完的书显示在"继续阅读"横向滚动栏

### 我的书架（`/shelf`）

- 入口：首页 header 🗂️ 图标 / 书籍详情页右上角
- 展示所有读过的书：封面 + 书名 + 作者 + 进度条 + % + 上次阅读日期
- 三个 Tab：全部 / 阅读中 / 已读完
- 顶部统计行：共 N 本 · 阅读中 N · 已读完 N
- 进度条：蓝色=进行中，绿色=已读完
- 每本书：[继续阅读/重读] [详情] 按钮

### 阅读器工具栏

| 格式 | 工具栏内容 |
|---|---|
| EPUB / MOBI | 🏠 ← 详情 上一页 **N/M页** 下一页 ☰ 📝 🔖 ｜ 右侧垂直进度条 |
| TXT | 🏠 ← 详情 字号 深色 ☰ 📝 🔖 |
| DOCX | 🏠 ← 详情 ☰ 📝 |
| PDF | 🏠 ← 详情（iframe 嵌入，无法追踪进度） |

**☰ 目录面板**（左侧滑出，280px）
- EPUB / MOBI：读取 epub.js `book.navigation.toc`；若无目录则从 spine 取前 30 章作为假目录
- TXT：扫描"第X章"等模式；无匹配时显示 0% / 10% … 90% 进度快跳
- DOCX：mammoth 转 HTML 后扫描 h1/h2/h3，点击 scrollIntoView 跳转
- 点击章节条目自动关闭面板并跳转；PDF 暂不支持

**EPUB/MOBI 右侧进度条**
- 28px 宽垂直滑块，固定在右侧边缘
- `generate()` 完成前：按百分比拖动；完成后：精确到位置点（`cfiFromPercentage`）
- 翻页时自动同步滑块位置

**📝 笔记面板**（右侧，右移 28px 避开进度条）
- 显示已有笔记列表（可删除）
- 输入框写笔记/摘录，保存时自动附加当前位置

**🔖 书签面板**（右侧，与笔记互斥）
- 5 色选择器：🔴红 🟠橙 🟢绿 🔵蓝 🟣紫（默认橙）
- 书签列表：彩色圆点 + 备注 + 位置，可跳转、删除

### 书籍上传

- 入口：首页 header ⬆ 按钮 → 拖拽/选文件 modal
- 支持：EPUB / PDF / TXT / DOCX / MOBI / AZW3，最大 200MB
- SHA256 去重（同一文件跳过，跳转到已有书籍详情）
- 上传后直接写入 `books.db`，立即在书库可见

### 相关书推荐

- 算法 1：同 `category2`，按置信度降序取前 10
- 算法 2：`fine_tags` Jaccard 相似度，扫 2000 条，取前 15，合并去重
- 5 分钟内存缓存

---

## API 端点（完整）

```
# 书库
GET  /api/books            筛选分页
GET  /api/featured         每日精选（?seed= 换批）
GET  /api/facets           分类/作者/年代等筛选项
GET  /api/book/:id         书籍详情
GET  /api/book/:id/related 相关书
GET  /api/random           随机一本
GET  /api/epub-proxy/:id   MOBI/AZW3 转 EPUB
POST /api/upload           书籍上传（multipart）

# 用户
POST /api/user/init                   建/更新用户
GET  /api/user/:id                    profile
PUT  /api/user/:id/name               改显示名
POST /api/user/:id/merge              合并另一 UUID

POST /api/user/:id/history            记录进度
GET  /api/user/:id/history            阅读历史列表
GET  /api/user/:id/history/:book_id   某本书进度

POST   /api/user/:id/bookmark         添加书签（含 color）
GET    /api/user/:id/bookmarks/:book_id
DELETE /api/user/:id/bookmark/:bm_id

POST   /api/user/:id/note             添加/更新笔记
GET    /api/user/:id/notes/:book_id
DELETE /api/user/:id/note/:note_id

POST /api/user/:id/rating             1-5 星评分
GET  /api/user/:id/export             导出 JSON
POST /api/user/:id/import             导入（合并模式）
```

---

## 关键路径

| 路径 | 用途 |
|------|------|
| `books_organizer/web.py` | **主源码**，所有 web 功能（约 3100 行） |
| `books_organizer/user_db.py` | 用户数据库 schema + resolve_user + 迁移 |
| `books_organizer/paths.py` | 路径配置（DB_PATH / USER_DB_PATH / UPLOAD_DIR 等） |
| `books_organizer/llm_tag.py` | LLM 标签生成（fine_tags，已标注 ~770 本） |
| `.claude/worktrees/affectionate-roentgen-787453/books_organizer/books.db` | 主数据库（39751 本） |
| `.claude/worktrees/affectionate-roentgen-787453/.venv/` | Python 环境（本地开发用） |
| `books_organizer-docker/` | Dockerfile.web / NAS 用 compose / Makefile |

---

## 下一步（待做）

### 优先级高

1. **llm-tag 全量标注** — 提升相关书推荐效果（当前覆盖率 ~2%）
   ```bash
   ssh nas 'docker run --rm \
     -e BOOKS_DATA_DIR=/data -e ANTHROPIC_API_KEY=sk-... \
     -v /volume1/docker/books_organizer/src/data:/data \
     books_organizer:latest python -m books_organizer llm-tag --concurrency 4'
   ```

2. ~~**书签在书籍详情页显示颜色**~~ — ✅ 已完成（web-0.8.6）

3. **评分聚合 + 用户统计** — 用户说"换一种做法"，具体方案下次 session 确认

### 优先级低

4. **上传后自动 extract** — 上传的书自动触发 pipeline 提取元数据（需 pipeline 容器）

5. **PDF 进度追踪** — 当前 PDF 用 iframe 嵌入，无法追踪页码；可改用 pdf.js 的 JS API

6. **书架排序** — `/shelf` 页目前按 last_read_at 排序，可增加"按进度"/"按书名"等排序选项

---

## 残留问题

1. `~/Library/LaunchAgents/com.bai.books_sync.plist` 引用不存在的脚本，建议 `rm -f` 清掉
2. `.claude/worktrees/affectionate-roentgen-787453/` 是旧 worktree，目前仍在用（.venv 和 books.db 在里面）
3. llm-tag 覆盖率约 2%，相关书推荐效果有限，需要跑全量
4. 本地开发需先挂载 `smb://admin@192.168.1.36/book` 到 `/Volumes/book`，否则书文件 404
