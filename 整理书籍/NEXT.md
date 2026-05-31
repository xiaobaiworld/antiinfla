# 整理书籍 — 进度与接续清单

> 这份文档是为了让下一个会话能直接从这里接续。  
> 最近更新：2026-05-31，commit `d800d90`

## 一句话现状

NAS 运行 `web-0.7.1`（http://192.168.1.44:8766/），功能完整：
- 首页每日精选（business/literature/humanities 优先，日期种子）
- 筛选：分类/二级/跨界/作者/年代/格式/拼音排序
- 在线阅读：**EPUB / PDF / TXT / DOCX / MOBI / AZW3** 全部支持
- 封面 bug 已修（send_file 改 .resolve()）

---

## 已完成功能总览

| 版本 | 功能 |
|------|------|
| web-0.6.0 | 拼音排序、跨界相关、出版年代、作者筛选、首页每日精选 |
| web-0.7.1 | 多格式阅读器（EPUB/PDF/TXT/DOCX/MOBI/AZW3）+ cover bug fix |

---

## 部署事实（权威）

| 项 | 值 |
|---|---|
| SSH | `ssh nas`（`bai@192.168.1.44:10022`，密钥 `~/.ssh/id_ed25519`） |
| 机器 | 绿联 DX4600，Linux x86_64，Docker 26.1.0 |
| compose 项目 | `/volume1/docker/books_organizer/src/`（项目名 `src`） |
| 当前容器 | `books_web` = `books_organizer:web-0.7.1`，端口 8766，healthy |
| 数据 | `src/data/books.db`（114M）+ `src/data/covers/`（49058 张） |
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

## 下一步：用户功能 + 书籍上传（本 session 未执行，留给下个 session）

### 背景和设计决策（本 session 已讨论确认）

#### 用户身份

- 首次访问自动生成 UUID 存 `localStorage`（匿名，按设备区分）
- 可设置显示名（纯标签，无密码）
- **关键需求：用户合并** — 同一人在不同浏览器/设备产生多个 UUID，需要能把它们合并成一个账号
  - 合并方式：用户手动输入另一个 UUID 或扫码，确认后服务端合并数据
- 数据导出（JSON）/ 导入（合并模式）
- 独立数据库：`user_data.db`（不混进 books.db）

#### 数据库 Schema（user_data.db）

```sql
CREATE TABLE users (
  id TEXT PRIMARY KEY,       -- UUID，localStorage 自动生成
  name TEXT,                 -- 显示名
  merged_into TEXT,          -- 合并到另一个 user_id（软删除）
  created_at REAL,
  last_seen REAL
);

CREATE TABLE user_aliases (
  alias_id TEXT PRIMARY KEY, -- 被合并的旧 UUID
  primary_id TEXT,           -- 主 UUID
  merged_at REAL
);

CREATE TABLE reading_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  book_id INTEGER,
  started_at REAL,
  last_read_at REAL,
  progress_pct REAL,         -- 0.0-1.0
  last_position TEXT,        -- EPUB: CFI; PDF: 页码; TXT: 字符偏移
  total_time_sec INTEGER
);

CREATE TABLE bookmarks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  book_id INTEGER,
  position TEXT,
  label TEXT,
  created_at REAL
);

CREATE TABLE notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT,
  book_id INTEGER,
  position TEXT,             -- 位置（可为空=整书笔记）
  text TEXT,
  created_at REAL,
  updated_at REAL
);

CREATE TABLE ratings (
  user_id TEXT,
  book_id INTEGER,
  rating INTEGER,            -- 1-5
  review TEXT,
  created_at REAL,
  PRIMARY KEY(user_id, book_id)
);
```

#### API 端点（待实现）

```
POST /api/user/init            # 首次访问建用户
GET  /api/user/:id             # 获取 profile
PUT  /api/user/:id/name        # 改显示名
POST /api/user/:id/merge       # 合并另一个 UUID 到本账号

POST /api/user/:id/history     # 记录阅读（书 ID + 位置 + 进度）
GET  /api/user/:id/history     # 阅读历史列表
GET  /api/user/:id/history/:book_id  # 某本书的进度（用于恢复阅读）

POST /api/user/:id/bookmark    # 添加书签
GET  /api/user/:id/bookmarks/:book_id
DELETE /api/user/:id/bookmark/:bm_id

POST /api/user/:id/note        # 添加/更新笔记
GET  /api/user/:id/notes/:book_id
DELETE /api/user/:id/note/:note_id

POST /api/user/:id/rating      # 评分
GET  /api/user/:id/export      # 导出全部数据（JSON）
POST /api/user/:id/import      # 导入（合并模式）
```

#### 前端改动

- header 右侧加"用户"图标 → 侧边栏：显示名、切换用户、合并账号、导出/导入
- 首页"继续阅读"区域（最近未读完的书，按 last_read_at 排序，最多 6 本）
- 首页精选：已读完的书降权，按历史分类偏好调整权重
- 书籍详情页：显示该用户的进度条、书签列表、笔记、评分
- 阅读器（EPUB/TXT）：翻页/滚动时自动 POST 进度（节流 5s）

---

### 书籍上传功能

#### 需求

当前书库全靠扫 `/books:ro` 目录。要支持用户通过 web 界面上传新书，扩充书库。

#### 设计方案

- 上传目标：NAS 上的一个可写目录（如 `/books/_上传/` 或单独 volume）
- 支持格式：EPUB / PDF / TXT / DOCX / MOBI / AZW3
- 上传后：自动触发 `books_organizer scan + extract`（pipeline 容器按需启动）
- 限制：单文件最大 200MB；同名文件跳过（用 SHA256 去重）

#### 实现步骤

1. `docker-compose.yml` 增加可写 volume（或改 books_share 为 rw）
2. web.py 增加 `POST /api/upload` 路由，接收 multipart，写入上传目录
3. 上传完成后在后台 subprocess 跑 `python -m books_organizer scan --incremental`
4. 前端：header 加"上传"按钮 → 拖拽或点选文件 → 进度条 → 完成提示

#### 注意

- NAS 的 CIFS 挂载目前是 `:ro`，上传需要改 volume 配置或新增独立可写目录
- pipeline 容器（全功能，含 calibre）负责 extract/classify，web 容器不含 calibre

---

### 相关书推荐 / 书籍标签（多维度）

#### 目标

对每本书生成/累积多维度标签，驱动"相关书"推荐：

| 维度 | 来源 | 示例 |
|------|------|------|
| 内容标签 | LLM 生成（已有 llm-tag 子命令） | `["价值投资", "芒格", "心理学"]` |
| 分类标签 | classify.py 结果 | `tech / AI机器学习` |
| 阅读热度 | reading_history 汇总 | 读过人数、平均进度 |
| 个人标签 | 用户自定义 + 笔记关键词 | `"必读"`, `"已读"`, `"重读"` |

#### 相关书算法（简单版，优先实现）

1. 同 category2（二级分类）的书，按置信度取 top 10
2. 共享 llm fine_tags 重叠最多的书（Jaccard 相似度）
3. 展示在书籍详情页"相关书籍"区（横向滚动卡片）

#### llm-tag 进度

- 已标注：770 / 39751（~2%）
- 剩余：38981 本
- 跑完全量需要：`python -m books_organizer llm-tag --concurrency 4`（约数小时）
- 可以在 NAS 上后台跑 pipeline 容器来完成

---

## 当前可立即运行的命令

```bash
cd /Users/bai/code/整理书籍

# 看数据库状态
BOOKS_DATA_DIR=.claude/worktrees/affectionate-roentgen-787453/books_organizer \
  .claude/worktrees/affectionate-roentgen-787453/.venv/bin/python \
  -m books_organizer status

# 启动本地 web（8766 端口）
BOOKS_DATA_DIR=.claude/worktrees/affectionate-roentgen-787453/books_organizer \
  .claude/worktrees/affectionate-roentgen-787453/.venv/bin/python \
  -m books_organizer web --port 8766

# llm-tag 全量（后台跑，可中断续跑）
BOOKS_DATA_DIR=.claude/worktrees/affectionate-roentgen-787453/books_organizer \
  .claude/worktrees/affectionate-roentgen-787453/.venv/bin/python \
  -m books_organizer llm-tag --concurrency 4
```

---

## 关键路径

| 路径 | 用途 |
|------|------|
| `books_organizer/web.py` | **主源码**，所有 web 功能在此单文件 |
| `books_organizer/llm_tag.py` | LLM 标签生成（770 本已标注） |
| `.claude/worktrees/affectionate-roentgen-787453/books_organizer/books.db` | 当前唯一数据库（39751 本） |
| `.claude/worktrees/affectionate-roentgen-787453/.venv/` | Python 环境 |
| `books_organizer-docker/` | Dockerfile.web / compose / Makefile |

---

## 下个 Session 的执行顺序（建议）

1. `Read NEXT.md`（就是这份）
2. 确认 NAS 健康：`curl http://192.168.1.44:8766/api/featured`
3. **优先执行：用户功能 P0**
   - 新建 `books_organizer/user_db.py`（Schema + 基础 CRUD）
   - web.py 增加用户 API 端点（参考上方设计）
   - 前端增加用户初始化（localStorage UUID）+ header 用户入口
   - 阅读器自动保存进度 + 书籍详情页显示进度
4. **然后：书籍上传**（需要先确认 NAS 可写目录方案）
5. **然后：相关书推荐**（先做同 category2 简单版）
6. **后台慢慢跑**：llm-tag 全量，积累数据为相关书推荐服务

---

## 残留问题

1. `~/Library/LaunchAgents/com.bai.books_sync.plist` 里引用不存在的脚本，建议 `rm -f` 清掉
2. `.claude/worktrees/affectionate-roentgen-787453/` 是旧 worktree，目前仍在用（.venv 和 books.db 在里面）
3. llm-tag 仅覆盖 2%，相关书推荐效果有限，需要跑全量
