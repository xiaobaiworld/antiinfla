-- books_organizer SQLite schema
-- 单一真源；所有阶段读写这一份库

CREATE TABLE IF NOT EXISTS files (
    id              INTEGER PRIMARY KEY,
    rel_path        TEXT NOT NULL UNIQUE,   -- 相对 root 的路径
    name            TEXT NOT NULL,
    ext             TEXT NOT NULL,          -- 小写不带点，如 "pdf"
    size            INTEGER NOT NULL,
    mtime           REAL NOT NULL,          -- 修改时间戳
    fingerprint     TEXT,                   -- size + head64k md5 的快指纹
    sha1            TEXT,                   -- 仅在去重阶段按需算
    kind            TEXT NOT NULL,          -- book / archive / other
    scanned_at      REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_ext ON files(ext);
CREATE INDEX IF NOT EXISTS idx_files_kind ON files(kind);
CREATE INDEX IF NOT EXISTS idx_files_fp ON files(fingerprint);

CREATE TABLE IF NOT EXISTS metadata (
    file_id         INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    title           TEXT,
    author          TEXT,
    isbn            TEXT,
    publisher       TEXT,
    pubdate         TEXT,
    language        TEXT,
    tags            TEXT,                   -- JSON array
    source          TEXT NOT NULL,          -- embedded / filename / pdftext / online / llm / none
    confidence      REAL NOT NULL,          -- 0.0–1.0
    extracted_at    REAL NOT NULL,
    -- 去重：同书的不同版本/格式归到同一 cluster
    cluster_key     TEXT,                   -- normalize(title)|normalize(primary_author)
    cluster_role    TEXT NOT NULL DEFAULT 'primary',  -- primary / variant
    primary_file_id INTEGER                 -- variant 指向其 primary 的 file_id
);

CREATE INDEX IF NOT EXISTS idx_meta_isbn ON metadata(isbn);
CREATE INDEX IF NOT EXISTS idx_meta_title ON metadata(title);
-- 集群相关索引在 db.init() 里 ALTER TABLE 之后创建

CREATE TABLE IF NOT EXISTS lookups (
    id              INTEGER PRIMARY KEY,
    query_key       TEXT NOT NULL UNIQUE,   -- isbn:xxx 或 title:xxx|author:yyy
    provider        TEXT NOT NULL,          -- douban / google_books / openlibrary
    response_json   TEXT NOT NULL,
    fetched_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS plan (
    id              INTEGER PRIMARY KEY,
    file_id         INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    target_rel_path TEXT NOT NULL,          -- 目标相对路径
    action          TEXT NOT NULL,          -- link / skip / unknown
    reason          TEXT,
    applied_at      REAL                    -- NULL = 未执行
);

CREATE INDEX IF NOT EXISTS idx_plan_action ON plan(action);
CREATE INDEX IF NOT EXISTS idx_plan_applied ON plan(applied_at);
