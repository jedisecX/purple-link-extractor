from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from purple.database import get_db


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_activity(conn, event: str, detail: str | None = None) -> None:
    conn.execute(
        "INSERT INTO activity (event, detail, created_at) VALUES (?, ?, ?)",
        (event, detail, utcnow()),
    )


def stats(db_path: str | Path) -> dict:
    with get_db(db_path) as conn:
        links = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        domains = conn.execute("SELECT COUNT(*) FROM domains").fetchone()[0]
        registered = conn.execute(
            "SELECT COUNT(DISTINCT registered_domain) FROM domains WHERE registered_domain IS NOT NULL AND registered_domain != ''"
        ).fetchone()[0]
        sources = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        queued = conn.execute("SELECT COUNT(*) FROM harvest_queue").fetchone()[0]
        last = conn.execute(
            "SELECT filename, imported_at FROM sources ORDER BY imported_at DESC LIMIT 1"
        ).fetchone()
        tld = conn.execute(
            """
            SELECT
              CASE
                WHEN hostname LIKE '%.gov' OR hostname LIKE '%.gov.%' THEN '.gov'
                WHEN hostname LIKE '%.edu' THEN '.edu'
                WHEN hostname LIKE '%.org' THEN '.org'
                WHEN hostname LIKE '%.net' THEN '.net'
                WHEN hostname LIKE '%.com' THEN '.com'
                ELSE 'other'
              END AS bucket,
              SUM(link_count) AS n
            FROM domains
            GROUP BY bucket
            ORDER BY n DESC
            """
        ).fetchall()
        growth = conn.execute(
            """
            SELECT substr(first_seen, 1, 7) AS month, COUNT(*) AS n
            FROM links
            WHERE first_seen IS NOT NULL
            GROUP BY month
            ORDER BY month
            LIMIT 24
            """
        ).fetchall()
        source_activity = conn.execute(
            """
            SELECT substr(imported_at, 1, 10) AS day, COUNT(*) AS n, SUM(urls_discovered) AS urls
            FROM sources
            GROUP BY day
            ORDER BY day DESC
            LIMIT 14
            """
        ).fetchall()
    return {
        "total_urls": links,
        "total_domains": domains,
        "registered_domains": registered,
        "source_files": sources,
        "queued": queued,
        "last_import": dict(last) if last else None,
        "tld_breakdown": [{"label": r["bucket"], "count": r["n"] or 0} for r in tld],
        "growth": [{"month": r["month"], "count": r["n"]} for r in growth],
        "source_activity": [
            {"day": r["day"], "sources": r["n"], "urls": r["urls"] or 0} for r in source_activity
        ],
    }


def list_urls(
    db_path: str | Path,
    q: str = "",
    domain: str = "",
    registered_domain: str = "",
    scheme: str = "",
    extension: str = "",
    source: str = "",
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    path_contains: str = "",
    limit: int = 50,
    offset: int = 0,
    after: int | None = None,
    include_total: bool = False,
) -> dict:
    limit = min(max(int(limit), 1), 200)
    offset = max(int(offset), 0)
    where = ["1=1"]
    args: list = []
    if q:
        where.append("(l.normalized_url LIKE ? OR l.hostname LIKE ? OR l.path LIKE ? OR l.query LIKE ? OR l.source_file LIKE ?)")
        like = f"%{q}%"
        args.extend([like, like, like, like, like])
    if domain:
        where.append("l.hostname = ?")
        args.append(domain)
    if registered_domain:
        where.append("l.registered_domain = ?")
        args.append(registered_domain)
    if scheme:
        where.append("l.scheme = ?")
        args.append(scheme.lower())
    if extension:
        ext = extension if extension.startswith(".") else f".{extension}"
        where.append("lower(l.path) LIKE ?")
        args.append(f"%{ext.lower()}")
    if source:
        where.append("l.source_file = ?")
        args.append(source)
    if status:
        where.append("COALESCE(l.status, 'DISCOVERED') = ?")
        args.append(status)
    if date_from:
        where.append("l.first_seen >= ?")
        args.append(date_from)
    if date_to:
        where.append("l.first_seen <= ?")
        args.append(date_to)
    if path_contains:
        where.append("l.path LIKE ?")
        args.append(f"%{path_contains}%")
    if after is not None:
        where.append("l.id < ?")
        args.append(int(after))
    clause = " AND ".join(where)
    sql = f"""
        SELECT l.id, l.normalized_url, l.original_url, l.scheme, l.hostname,
               l.registered_domain, l.path, l.query, l.source_file, l.first_seen,
               COALESCE(l.status, 'DISCOVERED') AS status
        FROM links l
        WHERE {clause}
        ORDER BY l.id DESC
        LIMIT ?
    """
    qargs = [*args, limit + 1]
    if after is None and offset:
        sql = sql.replace("LIMIT ?", "LIMIT ? OFFSET ?")
        qargs = [*args, limit + 1, offset]
    with get_db(db_path) as conn:
        total = None
        if include_total and after is None and offset == 0:
            total = conn.execute(
                f"SELECT COUNT(*) FROM links l WHERE {clause}", args
            ).fetchone()[0]
        rows = conn.execute(sql, qargs).fetchall()
    items = [dict(r) for r in rows[:limit]]
    has_more = len(rows) > limit
    next_cursor = items[-1]["id"] if items and has_more else None
    return {
        "items": items,
        "limit": limit,
        "offset": offset,
        "after": after,
        "next": next_cursor,
        "has_more": has_more,
        "total": total,
    }


def url_detail(db_path: str | Path, link_id: int) -> dict | None:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT *, COALESCE(status, 'DISCOVERED') AS status FROM links WHERE id=?",
            (link_id,),
        ).fetchone()
        if not row:
            return None
        sources = conn.execute(
            """
            SELECT s.id, s.filename, s.imported_at, ls.source_row, ls.source_column
            FROM link_sources ls
            JOIN sources s ON s.id = ls.source_id
            WHERE ls.link_id=?
            ORDER BY s.imported_at
            """,
            (link_id,),
        ).fetchall()
        queued = conn.execute(
            "SELECT status, priority, added_at FROM harvest_queue WHERE link_id=?",
            (link_id,),
        ).fetchone()
    data = dict(row)
    data["source_history"] = [dict(s) for s in sources]
    data["queue"] = dict(queued) if queued else None
    return data


def list_domains(db_path: str | Path, q: str = "", tld: str = "", limit: int = 50, offset: int = 0) -> dict:
    limit = min(max(int(limit), 1), 200)
    offset = max(int(offset), 0)
    where = ["1=1"]
    args: list = []
    if q:
        where.append("(hostname LIKE ? OR registered_domain LIKE ?)")
        like = f"%{q}%"
        args.extend([like, like])
    if tld == "other":
        where.append(
            "hostname NOT LIKE '%.gov' AND hostname NOT LIKE '%.edu' AND hostname NOT LIKE '%.org' "
            "AND hostname NOT LIKE '%.net' AND hostname NOT LIKE '%.com'"
        )
    elif tld:
        where.append("hostname LIKE ?")
        args.append(f"%{tld}")
    clause = " AND ".join(where)
    with get_db(db_path) as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM domains WHERE {clause}", args).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT d.id, d.hostname, d.registered_domain, d.link_count, d.first_seen, d.last_seen,
                   (SELECT COUNT(DISTINCT ls.source_id)
                    FROM links l JOIN link_sources ls ON ls.link_id=l.id
                    WHERE l.domain_id=d.id) AS source_count
            FROM domains d
            WHERE {clause}
            ORDER BY d.link_count DESC, d.hostname
            LIMIT ? OFFSET ?
            """,
            [*args, limit, offset],
        ).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "items": [dict(r) for r in rows]}


def list_sources(db_path: str | Path, limit: int = 50, offset: int = 0) -> dict:
    limit = min(max(int(limit), 1), 200)
    offset = max(int(offset), 0)
    with get_db(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        rows = conn.execute(
            """
            SELECT id, filename, file_path, file_size, file_hash, imported_at, status,
                   link_count, urls_discovered, urls_inserted, duplicates, invalid_urls
            FROM sources
            ORDER BY imported_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return {"total": total, "limit": limit, "offset": offset, "items": [dict(r) for r in rows]}


def source_detail(db_path: str | Path, source_id: int, limit: int = 50, offset: int = 0) -> dict | None:
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        if not row:
            return None
        domains = conn.execute(
            """
            SELECT COUNT(DISTINCT l.domain_id)
            FROM link_sources ls JOIN links l ON l.id=ls.link_id
            WHERE ls.source_id=?
            """,
            (source_id,),
        ).fetchone()[0]
        urls = conn.execute(
            """
            SELECT l.id, l.normalized_url, l.hostname, COALESCE(l.status,'DISCOVERED') AS status
            FROM link_sources ls JOIN links l ON l.id=ls.link_id
            WHERE ls.source_id=?
            ORDER BY l.id DESC
            LIMIT ? OFFSET ?
            """,
            (source_id, limit, offset),
        ).fetchall()
        url_total = conn.execute(
            "SELECT COUNT(*) FROM link_sources WHERE source_id=?", (source_id,)
        ).fetchone()[0]
    data = dict(row)
    data["domain_count"] = domains
    data["urls"] = [dict(u) for u in urls]
    data["url_total"] = url_total
    return data


def recent_activity(db_path: str | Path, limit: int = 40) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT event, detail, created_at FROM activity ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def queue_list(db_path: str | Path, limit: int = 50, offset: int = 0) -> dict:
    with get_db(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM harvest_queue").fetchone()[0]
        rows = conn.execute(
            """
            SELECT q.id, q.status, q.priority, q.added_at, l.id AS link_id,
                   l.normalized_url, l.hostname, l.path
            FROM harvest_queue q
            JOIN links l ON l.id=q.link_id
            ORDER BY CASE q.priority WHEN 'HIGH' THEN 0 WHEN 'NORMAL' THEN 1 ELSE 2 END, q.id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return {"total": total, "items": [dict(r) for r in rows]}


def queue_add(db_path: str | Path, link_ids: list[int], priority: str = "NORMAL") -> int:
    added = 0
    now = utcnow()
    pri = priority if priority in {"LOW", "NORMAL", "HIGH"} else "NORMAL"
    with get_db(db_path) as conn:
        for lid in link_ids:
            cur = conn.execute(
                "INSERT OR IGNORE INTO harvest_queue (link_id, status, priority, added_at) VALUES (?, 'QUEUED', ?, ?)",
                (lid, pri, now),
            )
            if cur.rowcount:
                added += 1
                conn.execute("UPDATE links SET status='QUEUED' WHERE id=?", (lid,))
        if added:
            log_activity(conn, "HARVEST QUEUED", f"{added} urls")
        conn.commit()
    return added


def queue_remove(db_path: str | Path, ids: list[int]) -> int:
    with get_db(db_path) as conn:
        n = 0
        for qid in ids:
            row = conn.execute("SELECT link_id FROM harvest_queue WHERE id=?", (qid,)).fetchone()
            conn.execute("DELETE FROM harvest_queue WHERE id=?", (qid,))
            if row:
                conn.execute(
                    "UPDATE links SET status='DISCOVERED' WHERE id=? AND status='QUEUED'",
                    (row["link_id"],),
                )
                n += 1
        conn.commit()
    return n


def queue_clear(db_path: str | Path) -> None:
    with get_db(db_path) as conn:
        conn.execute(
            "UPDATE links SET status='DISCOVERED' WHERE id IN (SELECT link_id FROM harvest_queue)"
        )
        conn.execute("DELETE FROM harvest_queue")
        conn.commit()


def save_search(db_path: str | Path, name: str, query: str, filters: dict) -> int:
    with get_db(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO saved_searches (name, query, filters, created_at) VALUES (?, ?, ?, ?)",
            (name, query, json.dumps(filters), utcnow()),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_saved_searches(db_path: str | Path) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT id, name, query, filters, created_at FROM saved_searches ORDER BY id DESC"
        ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        try:
            item["filters"] = json.loads(item["filters"] or "{}")
        except json.JSONDecodeError:
            item["filters"] = {}
        out.append(item)
    return out
