from __future__ import annotations

from pathlib import Path

from purple.database import get_db


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def print_import_stats(stats, db_path: Path | None = None) -> str:
    db_size = ""
    if db_path and Path(db_path).is_file():
        db_size = f"{Path(db_path).stat().st_size:,} bytes"
    rate = 0.0
    if stats.elapsed > 0:
        rate = stats.urls_discovered / stats.elapsed
    lines = [
        "PURPLE LINK EXTRACTOR",
        "=====================",
        "",
        f"Files processed:     {stats.files_processed:>12,}",
        f"Files skipped:       {stats.files_skipped:>12,}",
        f"URLs discovered:     {stats.urls_discovered:>12,}",
        f"Unique URLs:         {stats.unique_urls:>12,}",
        f"Duplicates:          {stats.duplicates:>12,}",
        f"Invalid URLs:        {stats.invalid_urls:>12,}",
        f"Unique domains:      {stats.unique_domains:>12,}",
        "",
        f"HTTP URLs:           {stats.http_urls:>12,}",
        f"HTTPS URLs:          {stats.https_urls:>12,}",
        "",
        f"Processing time:     {format_duration(stats.elapsed):>12}",
        f"Processing rate:     {rate:>12,.0f} url/s",
    ]
    if db_size:
        lines.append(f"Database size:       {db_size:>12}")
    text = "\n".join(lines)
    print(text)
    return text


def db_overview(db_path: str | Path) -> dict:
    with get_db(db_path) as conn:
        links = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        domains = conn.execute("SELECT COUNT(*) FROM domains").fetchone()[0]
        sources = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        schemes = conn.execute(
            "SELECT scheme, COUNT(*) AS n FROM links GROUP BY scheme ORDER BY n DESC"
        ).fetchall()
        top = conn.execute(
            "SELECT hostname, link_count FROM domains ORDER BY link_count DESC, hostname LIMIT 20"
        ).fetchall()
    return {
        "links": links,
        "domains": domains,
        "sources": sources,
        "schemes": [(r["scheme"], r["n"]) for r in schemes],
        "top_domains": [(r["hostname"], r["link_count"]) for r in top],
    }


def list_domains(db_path: str | Path, limit: int = 100, offset: int = 0):
    with get_db(db_path) as conn:
        return conn.execute(
            "SELECT hostname, registered_domain, link_count FROM domains "
            "ORDER BY link_count DESC, hostname LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()


def domain_links(db_path: str | Path, hostname: str, limit: int = 100, offset: int = 0):
    with get_db(db_path) as conn:
        info = conn.execute(
            "SELECT hostname, registered_domain, link_count FROM domains "
            "WHERE hostname=? OR registered_domain=? ORDER BY hostname",
            (hostname, hostname),
        ).fetchall()
        links = conn.execute(
            "SELECT l.normalized_url FROM links l "
            "JOIN domains d ON d.id=l.domain_id "
            "WHERE d.hostname=? OR d.registered_domain=? "
            "ORDER BY l.normalized_url LIMIT ? OFFSET ?",
            (hostname, hostname, limit, offset),
        ).fetchall()
    return info, [r["normalized_url"] for r in links]


def search_links(db_path: str | Path, query: str, limit: int = 100):
    like = f"%{query}%"
    with get_db(db_path) as conn:
        return conn.execute(
            "SELECT normalized_url, hostname FROM links "
            "WHERE normalized_url LIKE ? OR hostname LIKE ? OR registered_domain LIKE ? "
            "ORDER BY hostname, normalized_url LIMIT ?",
            (like, like, like, limit),
        ).fetchall()
