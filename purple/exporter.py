from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from purple.database import get_db

log = logging.getLogger("purple")


def _safe_dir_name(name: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in ".-_" else "_" for c in name)
    cleaned = cleaned.lstrip(".")
    return cleaned or "unknown"


def export_all(db_path: str | Path, dest: Path, fmt: str = "csv") -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT l.normalized_url, l.original_url, l.scheme, l.hostname, "
            "l.registered_domain, l.path, l.query, l.first_seen, l.source_file "
            "FROM links l ORDER BY l.hostname, l.normalized_url"
        ).fetchall()
        if fmt == "json":
            payload = [dict(r) for r in rows]
            dest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        else:
            with dest.open("w", encoding="utf-8", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(
                    [
                        "normalized_url",
                        "original_url",
                        "scheme",
                        "hostname",
                        "registered_domain",
                        "path",
                        "query",
                        "first_seen",
                        "source_file",
                    ]
                )
                for r in rows:
                    writer.writerow([r[k] for k in r.keys()])
    return dest


def export_domain(db_path: str | Path, hostname: str, dest: Path, fmt: str = "txt") -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT l.normalized_url FROM links l "
            "JOIN domains d ON d.id = l.domain_id "
            "WHERE d.hostname = ? OR d.registered_domain = ? "
            "ORDER BY l.normalized_url",
            (hostname, hostname),
        ).fetchall()
        urls = [r["normalized_url"] for r in rows]
        if fmt == "csv":
            with dest.open("w", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["url"])
                for u in urls:
                    w.writerow([u])
        elif fmt == "json":
            dest.write_text(json.dumps(urls, indent=2), encoding="utf-8")
        else:
            dest.write_text("\n".join(urls) + ("\n" if urls else ""), encoding="utf-8")
    return dest


def export_domain_directory(db_path: str | Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    with get_db(db_path) as conn:
        domains = conn.execute(
            "SELECT id, hostname, registered_domain, first_seen, last_seen, link_count "
            "FROM domains ORDER BY link_count DESC, hostname"
        ).fetchall()
        for d in domains:
            folder = out_dir / _safe_dir_name(d["hostname"])
            folder.mkdir(parents=True, exist_ok=True)
            links = conn.execute(
                "SELECT normalized_url, original_url, scheme, path, query, first_seen "
                "FROM links WHERE domain_id=? ORDER BY normalized_url",
                (d["id"],),
            ).fetchall()
            urls = [r["normalized_url"] for r in links]
            (folder / "links.txt").write_text("\n".join(urls) + ("\n" if urls else ""), encoding="utf-8")
            with (folder / "links.csv").open("w", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh)
                w.writerow(["normalized_url", "original_url", "scheme", "path", "query", "first_seen"])
                for r in links:
                    w.writerow([r["normalized_url"], r["original_url"], r["scheme"], r["path"], r["query"], r["first_seen"]])
            meta = {
                "hostname": d["hostname"],
                "registered_domain": d["registered_domain"],
                "first_seen": d["first_seen"],
                "last_seen": d["last_seen"],
                "link_count": d["link_count"],
            }
            (folder / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return out_dir
