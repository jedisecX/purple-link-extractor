from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from purple.database import get_db
from purple.domains import parse_domain
from purple.extractor import ExtractedURL, iter_file_urls
from purple.normalizer import normalize

log = logging.getLogger("purple")

SUPPORTED_SUFFIXES = {".txt", ".csv"}


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def file_sha256(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def discover_files(target: Path, recursive: bool) -> list[Path]:
    if target.is_file():
        return [target]
    if not target.is_dir():
        return []
    pattern = "**/*" if recursive else "*"
    files = []
    for p in sorted(target.glob(pattern)):
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES:
            files.append(p)
    return files


@dataclass
class ImportStats:
    files_processed: int = 0
    files_skipped: int = 0
    urls_discovered: int = 0
    unique_urls: int = 0
    duplicates: int = 0
    unique_domains: int = 0
    http_urls: int = 0
    https_urls: int = 0
    invalid_urls: int = 0
    started: float = field(default_factory=time.perf_counter)
    elapsed: float = 0.0

    def finish(self) -> None:
        self.elapsed = time.perf_counter() - self.started


class Importer:
    def __init__(
        self,
        db_path: str | Path,
        batch_size: int = 1000,
        accepted_schemes: list[str] | None = None,
    ):
        self.db_path = Path(db_path)
        self.batch_size = max(1, int(batch_size))
        self.accepted_schemes = [s.lower() for s in (accepted_schemes or ["http", "https"])]

    def import_path(self, target: Path, recursive: bool = False) -> ImportStats:
        stats = ImportStats()
        files = discover_files(target, recursive)
        log.info("Files discovered: %s", len(files))
        with get_db(self.db_path) as conn:
            for path in files:
                try:
                    self._import_file(conn, path, stats)
                except KeyboardInterrupt:
                    conn.commit()
                    log.warning("Interrupted during %s — database committed", path)
                    raise
                except Exception:
                    log.exception("Failed processing %s", path)
                    conn.rollback()
            self._refresh_counts(conn)
            stats.unique_urls = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
            stats.unique_domains = conn.execute("SELECT COUNT(*) FROM domains").fetchone()[0]
            row = conn.execute(
                "SELECT "
                "SUM(CASE WHEN scheme='http' THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN scheme='https' THEN 1 ELSE 0 END) "
                "FROM links"
            ).fetchone()
            stats.http_urls = row[0] or 0
            stats.https_urls = row[1] or 0
        stats.finish()
        return stats

    def _import_file(self, conn, path: Path, stats: ImportStats) -> None:
        size = path.stat().st_size
        digest = file_sha256(path)
        existing = conn.execute(
            "SELECT id, status FROM sources WHERE file_hash=? AND file_size=?",
            (digest, size),
        ).fetchone()
        if existing and existing["status"] == "complete":
            log.info("Skipping (already imported): %s", path)
            stats.files_skipped += 1
            return

        now = utcnow()
        if existing:
            source_id = existing["id"]
            conn.execute(
                "UPDATE sources SET status='in_progress', imported_at=?, filename=?, file_path=? WHERE id=?",
                (now, path.name, str(path.resolve()), source_id),
            )
        else:
            cur = conn.execute(
                "INSERT INTO sources (filename, file_path, file_size, file_hash, imported_at, status) "
                "VALUES (?, ?, ?, ?, ?, 'in_progress')",
                (path.name, str(path.resolve()), size, digest, now),
            )
            source_id = cur.lastrowid
        conn.commit()

        log.info("Processing: %s", path)
        discovered = inserted = duplicates = invalid = 0
        batch = 0

        for extracted in iter_file_urls(path):
            discovered += 1
            stats.urls_discovered += 1
            norm = normalize(extracted.raw, self.accepted_schemes)
            if not norm.valid:
                invalid += 1
                stats.invalid_urls += 1
                continue
            added = self._upsert_link(conn, source_id, extracted, norm, now)
            if added:
                inserted += 1
            else:
                duplicates += 1
                stats.duplicates += 1
            batch += 1
            if batch >= self.batch_size:
                conn.execute(
                    "UPDATE sources SET urls_discovered=?, urls_inserted=?, duplicates=?, "
                    "invalid_urls=?, last_checkpoint=? WHERE id=?",
                    (discovered, inserted, duplicates, invalid, utcnow(), source_id),
                )
                conn.commit()
                log.info("Checkpoint committed")
                batch = 0

        conn.execute(
            "UPDATE sources SET status='complete', link_count=?, urls_discovered=?, "
            "urls_inserted=?, duplicates=?, invalid_urls=?, last_checkpoint=? WHERE id=?",
            (inserted, discovered, inserted, duplicates, invalid, utcnow(), source_id),
        )
        conn.commit()
        stats.files_processed += 1
        log.info("Extracted %s URLs", discovered)
        log.info("New URLs: %s", inserted)
        log.info("Duplicates: %s", duplicates)

    def _upsert_link(self, conn, source_id: int, extracted: ExtractedURL, norm, now: str) -> bool:
        parts = parse_domain(norm.hostname)
        domain_row = conn.execute(
            "SELECT id FROM domains WHERE hostname=?", (parts.hostname,)
        ).fetchone()
        if domain_row:
            domain_id = domain_row["id"]
            conn.execute(
                "UPDATE domains SET last_seen=? WHERE id=?",
                (now, domain_id),
            )
        else:
            cur = conn.execute(
                "INSERT INTO domains (hostname, registered_domain, first_seen, last_seen, link_count) "
                "VALUES (?, ?, ?, ?, 0)",
                (parts.hostname, parts.registered_domain, now, now),
            )
            domain_id = cur.lastrowid

        existing = conn.execute(
            "SELECT id FROM links WHERE normalized_url=?",
            (norm.normalized,),
        ).fetchone()
        if existing:
            link_id = existing["id"]
            conn.execute("UPDATE links SET last_seen=? WHERE id=?", (now, link_id))
            is_new = False
        else:
            cur = conn.execute(
                "INSERT INTO links (domain_id, original_url, normalized_url, scheme, hostname, "
                "registered_domain, port, path, query, fragment, first_seen, last_seen, "
                "source_file, source_row, source_column) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    domain_id,
                    extracted.raw,
                    norm.normalized,
                    norm.scheme,
                    norm.hostname,
                    parts.registered_domain,
                    norm.port,
                    norm.path,
                    norm.query,
                    norm.fragment,
                    now,
                    now,
                    extracted.source_file,
                    extracted.source_row,
                    extracted.source_column,
                ),
            )
            link_id = cur.lastrowid
            is_new = True

        conn.execute(
            "INSERT OR IGNORE INTO link_sources (link_id, source_id, source_row, source_column) "
            "VALUES (?, ?, ?, ?)",
            (link_id, source_id, extracted.source_row, extracted.source_column),
        )
        return is_new

    def _refresh_counts(self, conn) -> None:
        conn.execute(
            "UPDATE domains SET link_count = ("
            "SELECT COUNT(*) FROM links WHERE links.domain_id = domains.id)"
        )
        conn.commit()
