# 整理书籍 — 进度与接续清单

> 这份文档是为了让下一个会话能直接从这里接续。  
> 最近更新 commit:`b0b1cb5`(2026-05-29)

## 一句话现状

books_organizer 源码 + web 新功能(拼音 / 跨界相关 / 出版年代 / 作者筛选)已在 `main`;
**最新版 `web-0.6.0` 已部署到绿联 NAS 并 healthy 运行中** → http://192.168.1.44:8766/

**2026-05-30 本会话:把最新版部署上了 NAS,接管了之前的 0.5.0。**
- 之前 NAS 上跑的是 `web-0.5.0`(旧代码,facets 无 decades、db 无 pub_year/title_sort 列)——
  那是早期试验版,NEXT.md 旧版本不知道它的存在。
- 本次:同步最新源码 + 推最新 db(114M,39751 行,pub_year/title_sort 齐全)→ 在 NAS 上构建
  `web-0.6.0` → 切换上线 → 全功能验证(decades / decade=2020→509 / 拼音 / 跨界相关 / 封面)通过。

**接下来可做**:E 项细粒度三级标签(数据问题,见下);或把本会话改动 commit(见下)。

---

## NAS 部署事实(权威,替代旧的"待办 A-D")

| 项 | 值 |
|---|---|
| SSH | `ssh nas`(已在 `~/.ssh/config`:`bai@192.168.1.44:10022`,密钥 `~/.ssh/id_ed25519`) |
| 机器 | 绿联 DX4600,Linux **x86_64**,Docker 26.1.0 / compose v2.26.1 |
| compose 项目 | `/volume1/docker/books_organizer/src/`(项目名 `src`),`.env` 设 `TAG=web-0.6.0 HOST_PORT=8766` |
| 运行容器 | `books_web` = `books_organizer:web-0.6.0`,端口 **8766→8765**,healthy |
| 数据 | `src/data/books.db`(114M)+ `src/data/covers/`(49058,与 Mac 一致) |
| 书源 | external named volume `books_share` → CIFS `//192.168.1.36/book`(挂 `/books:ro`) |
| 构建方式 | **在 NAS 上** `cd src && docker build -f Dockerfile.web -t books_organizer:web-0.6.0 .`(NAS 能到 pypi;Dockerfile.web 已加 `pypinyin`) |

### 回滚(若 0.6.0 出问题)
```bash
ssh nas 'cd /volume1/docker/books_organizer/src
  # 代码+镜像回滚:
  TAG=web-0.5.0 docker compose up -d web
  # 若还要回滚数据:
  docker compose stop web
  cp -p data/books.db.pre060.* data/books.db   # 旧 db(5/26,无 pub_year 列)
  TAG=web-0.5.0 docker compose up -d web'
```
备份物:`src/data/books.db.pre060.*`(旧 db)、`src.bak.pre060/`(旧 src)、镜像 `web-0.1.0~0.5.0` 均在。

### 下次更新版本的标准流程(code+data)
1. Mac 上 `VACUUM INTO` 出干净 db(见下"给新书回填"后)
2. `tar czf - -C books_organizer --exclude=__pycache__ . | ssh nas 'cd .../src/books_organizer && tar xzf -'`(同步源码;**rsync/scp 在这台 NAS 路径解析有 bug,用 tar/cat over ssh**)
3. `ssh nas 'cat > .../src/data/books.db.new' < 干净db` 然后 cutover(stop web → rm -f books.db-wal/-shm → mv → up)
4. NAS 上 bump `.env` 的 TAG,`docker build` 新 tag,`docker compose up -d web`

---

## 本会话修改待提交(未 commit)

| 文件 | 改动 |
|---|---|
| `books_organizer-docker/Dockerfile` | `COPY books_organizer/ ...` → `COPY --from=books_organizer . ...`(用 Makefile 的命名 build context;原写法必然构建失败) |
| `books_organizer-docker/Dockerfile.web` | 同上 |

提交建议:`fix(books_organizer-docker): Dockerfile 用命名 build context 复制源码`

### 本会话已生成的本地产物(未跟踪)
- `docker-demo/docker-demo-0.1.0.tar.gz`(47M,steps 5-8 待 scp 上 NAS)
- `books_organizer-docker/data/books.db`(114M,VACUUM INTO 的一致副本,39751 行)
- 镜像:`docker-demo:0.1.0`、`books-organizer-web:0.1.0`(均 amd64)
- 容器 `books-organizer-web` 当前在 8765 端口运行中,浏览器可开 http://localhost:8765

---

## 目录与关键路径

| 路径 | 用途 |
|---|---|
| `/Users/bai/code/整理书籍/books_organizer/` | **主源码包**(已纳入 git) |
| `/Users/bai/code/整理书籍/books_organizer-docker/` | 容器化资产(Dockerfile / compose / Makefile / REFACTOR-PLAN.md) |
| `/Users/bai/code/整理书籍/docker-demo/` | 部署链路验证项目(8 步过完即删) |
| `/Users/bai/code/整理书籍/.claude/worktrees/affectionate-roentgen-787453/` | 旧 worktree;**源码已合并,这里只剩 .venv 和 books.db**(数据未迁移) |
| `/Users/bai/code/整理书籍/.claude/worktrees/.../books_organizer/books.db` | **当前唯一的数据库**(35k+ 书),pipeline/web 都读这里 |
| `/Users/bai/code/整理书籍/.claude/worktrees/.../.venv/` | 当前唯一可用的 Python 环境(Python 3.11 + 全部依赖) |
| `git remote` | `github-2:xiaobaiworld/antiinfla.git`(此仓库托管多个项目,书籍只是其中一个目录) |

---

## 当前可立即运行的命令

所有命令都已验证可跑。把这些当成"接续后第一件事"。

### 看数据库进度

```bash
cd /Users/bai/code/整理书籍

BOOKS_DATA_DIR=.claude/worktrees/affectionate-roentgen-787453/books_organizer \
.claude/worktrees/affectionate-roentgen-787453/.venv/bin/python \
-m books_organizer status

# 期望输出:files=201981+, metadata=39751, lookups=*, plans=*
```

### 启动 web 站(本地浏览器)

```bash
cd /Users/bai/code/整理书籍

BOOKS_DATA_DIR=.claude/worktrees/affectionate-roentgen-787453/books_organizer \
.claude/worktrees/affectionate-roentgen-787453/.venv/bin/python \
-m books_organizer web --port 8766

# 然后开浏览器 http://localhost:8766
```

### 给新书回填拼音/年代字段

```bash
BOOKS_DATA_DIR=.claude/worktrees/affectionate-roentgen-787453/books_organizer \
.claude/worktrees/affectionate-roentgen-787453/.venv/bin/python \
-m books_organizer reindex
# 默认只补空值;39751 行 ~2 秒。--force 全表重算
```

---

## 已完成功能(已在 main 上)

### 1. 源码 env 化(REFACTOR-PLAN.md 全部 5+1 项)
- `paths.py` 集中所有路径,通过 `BOOKS_ROOT / BOOKS_DATA_DIR / CALIBRE_EBOOK_META` 等 env 覆盖
- 本地默认值 = 原值,行为零变化
- 容器里通过 `docker-compose.yml` 的 environment 覆盖

### 2. web 新筛选/排序(commit `b0b1cb5`)
- **拼音排序**(`?sort=pinyin`):预计算 `title_sort` 列,数字 → 字母 → 中文按拼音 A-Z
- **出版年代**:
  - `?sort=pub_year_desc` / `pub_year_asc` 排序
  - `?decade=2020` 筛十年代(2020s=509、2010s=10976、2000s=2995)
- **作者下拉**:facets 返回 top80,UI 直接选
- **跨界相关**(原称"三级标签"):category2 下显示相关二级分类,可交叉筛选
  - 例:`humanities/国学经典` 下的跨界相关包含 `书法(243) / 中医(144) / 散文随笔(77)`

### 3. 部署资产 + 验证 demo
- `books_organizer-docker/`:Dockerfile(全功能,含 calibre)、Dockerfile.web(轻量 web only)、compose、Makefile(build/save/scp/deploy/migrate-db/rollback)
- `docker-demo/`:Flask 3-route 最小应用,验证 Mac → NAS 部署链路

---

## 待办(按优先级)

### A. docker-demo 8 步验收 ← **下一步从这里开始**

详见 `docker-demo/docs/CHECKLIST.md`。需要 NAS 信息(暂未提供)。

```bash
cd /Users/bai/code/整理书籍/docker-demo
make build VERSION=0.1.0   # step 1
make local-run              # step 2(curl /health 看 ok:true)
make local-stop             # step 3
make save                   # step 4
# step 5-8 需要 NAS_USER@NAS_IP 和 NAS_DIR
make deploy NAS=??? NAS_DIR=???
```

**问用户**:绿联 NAS 的 `ssh user@host` 和容器目录?

### B. books_organizer 容器化 local-test

```bash
cd /Users/bai/code/整理书籍/books_organizer-docker
make build-web              # 只构 web 镜像(快)
make local-test             # 用本地 books.db 起 web 容器
# 浏览器开 http://localhost:8765 应该看到 39751 本书
```

注意:`docker-compose.yml` 里 `volumes: ./data:/data`,要先把 books.db 软链或复制到 `books_organizer-docker/data/`。

### C. 数据迁移到 NAS

```bash
make migrate-db NAS=??? NAS_DIR=???
# 内部:WAL checkpoint → rsync books.db + covers/ 到 NAS
```

### D. NAS 部署 + 接管

```bash
make deploy VERSION=0.2.0 NAS=??? NAS_DIR=???
# build + save + scp + ssh load + compose up
```

### E. 真正的细粒度三级标签(数据问题)

**当前问题**:`metadata.subjects` 是 classify 的二级候选数组(不是细粒度标签),`metadata.tags` 是 PDF 元数据(无意义),豆瓣 lookup 返回的 `tags=[]` 是空的。

**走法**(尚未实施):
- 重新跑豆瓣 lookup 拿真正的 tags(豆瓣 API 可能限流/变更,需先测)
- 或用 LLM(claude/gpt) 给 39751 本书生成细粒度标签 — 预算/时间需评估
- 拿到数据后,把 web.py 的"跨界相关"分支补一个真正的三级 subjects 入口

---

## 关键决策记录

### 数据库放哪
当前 books.db 在 worktree 下,**没有跟仓库一起 commit**(.gitignore 排除 `*.db`)。原因:35k 本书的 DB 几百 MB,放 git 不合适。后续两种方案:
- 留 Mac 本地,每次 sync 到 NAS(已写好 `make migrate-db`)
- 还是 NAS 上跑 pipeline 生成 — 但绿联出墙不通(用户已确认),lookup 必须留在 Mac

### 部署模式
`docker-compose.yml` 设计为:**web 常驻 + pipeline 按需触发**(profiles: ["manual"])。
- web 容器:轻量(不要 calibre,启动快)
- pipeline 容器:全功能(含 calibre),手动 `docker compose run pipeline scan` / `extract` 等

### 三级 = "跨界相关"
经讨论确认:UI 上"三级下拉"叫"跨界相关",因为底层 subjects 数据不是细粒度标签。等到 E 项完成才能改回真正的三级。

---

## 环境与依赖

### 系统依赖
- macOS Tahoe(M1)
- Homebrew Python 3.11(用 venv 隔离)
- Calibre.app(用于抽 mobi/azw 元数据,Mac 本地路径写死在 paths.py 默认值)
- `/opt/homebrew/bin/codex-acp`、`/opt/homebrew/bin/claude-agent-acp`(本会话刚装,两台机器路径一致)

### Python 依赖(`books_organizer-docker/requirements.txt`)
```
flask>=3.0
requests>=2.31
pypdf>=4.0
ebooklib>=0.18
pypinyin>=0.50
```

### 数据
- `files` 表:~201981(扫盘原始)
- `metadata` 表:~39751 主版本(已 extract + lookup + dedupe)
- 一级分类 100% 覆盖(8 类:tech/business/humanities/literature/practical/education/reference/other)
- 二级分类 80.8% 覆盖(30+ 子类)
- pubdate 75.8% 覆盖(ISO 字符串)
- title_sort + pub_year 100% 回填(本会话刚做)

---

## 残留问题(不阻塞,可清理)

1. **launchd 异常守护**:`com.bai.books_sync` 这个 LaunchAgent 引用了不存在的 `sync_supervisor.py`,本会话已 `launchctl unload`,但 plist 文件还在 `~/Library/LaunchAgents/com.bai.books_sync.plist`。建议手动 `rm -f`,否则下次登录又会启动报错。

2. **本会话曾出现两个目录被同步抹除**:`docker-demo/` 整个目录、`books_organizer-docker/` 大部分文件,只剩 `scripts/`(里面只有 launchd 日志)。**已根据上下文重建**,但 commit `0e71d5e` 重建的内容**可能跟原版有细微差异**(原内容没在 git,无法对比)。如果发现 Dockerfile/Makefile 行为异常,这是原因之一。

3. **`books_organizer-docker/scripts/` 残留**:只有两个 launchd 日志文件(`launchd.err.log` / `launchd.out.log`),无业务用途。git 不跟踪(*.log 被 ignore),手动 `rm -rf` 即可。

4. **旧 worktree**:`.claude/worktrees/affectionate-roentgen-787453/` 这个 worktree 当前还在用(.venv 和 books.db 都在里面)。一旦把 books.db 迁出 + 主仓建独立 .venv,worktree 就可以 `git worktree remove` 删掉。

---

## 给新会话的开场建议

新会话开始时,建议你直接说:

> "继续做整理书籍项目,从 NEXT.md 接续。第一步先 XXX。"

新 session 的 AI 应当:
1. `Read /Users/bai/code/整理书籍/NEXT.md`(就是这份)
2. `Read /Users/bai/code/整理书籍/README.md` 看目录结构
3. 看一眼 `git log --oneline -5`(主仓在 `/Users/bai/code`)确认最新 commit
4. 根据 "待办" 部分对话题展开
