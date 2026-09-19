from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS domains (
    id INTEGER PRIMARY KEY,
    hostname TEXT NOT NULL UNIQUE,
    registered_domain TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    link_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    file_path TEXT,
    file_size INTEGER,
    file_hash TEXT,
    imported_at TEXT NOT NULL,
    link_count INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    urls_discovered INTEGER DEFAULT 0,
    urls_inserted INTEGER DEFAULT 0,
    duplicates INTEGER DEFAULT 0,
    invalid_urls INTEGER DEFAULT 0,
    last_checkpoint TEXT,
    UNIQUE(file_hash, file_size)
);

CREATE TABLE IF NOT EXISTS links (
    id INTEGER PRIMARY KEY,
    domain_id INTEGER NOT NULL,
    original_url TEXT NOT NULL,
    normalized_url TEXT NOT NULL UNIQUE,
    scheme TEXT,
    hostname TEXT,
    registered_domain TEXT,
    port INTEGER,
    path TEXT,
    query TEXT,
    fragment TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    source_file TEXT,
    source_row INTEGER,
    source_column TEXT,
    FOREIGN KEY(domain_id) REFERENCES domains(id)
);

CREATE TABLE IF NOT EXISTS link_sources (
    id INTEGER PRIMARY KEY,
    link_id INTEGER NOT NULL,
    source_id INTEGER NOT NULL,
    source_row INTEGER,
    source_column TEXT,
    FOREIGN KEY(link_id) REFERENCES links(id),
    FOREIGN KEY(source_id) REFERENCES sources(id),
    UNIQUE(link_id, source_id, source_row, source_column)
);

CREATE INDEX IF NOT EXISTS idx_links_domain_id ON links(domain_id);
CREATE INDEX IF NOT EXISTS idx_links_hostname ON links(hostname);
CREATE INDEX IF NOT EXISTS idx_links_registered_domain ON links(registered_domain);
CREATE INDEX IF NOT EXISTS idx_links_first_seen ON links(first_seen);
CREATE INDEX IF NOT EXISTS idx_links_scheme ON links(scheme);
CREATE INDEX IF NOT EXISTS idx_domains_registered ON domains(registered_domain);
CREATE INDEX IF NOT EXISTS idx_sources_hash ON sources(file_hash);
CREATE INDEX IF NOT EXISTS idx_link_sources_source ON link_sources(source_id);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA temp_store = MEMORY")
    return conn


def initialize(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


@contextmanager
def get_db(db_path: str | Path):
    conn = connect(db_path)
    try:
        initialize(conn)
        yield conn
    finally:
        conn.close()
