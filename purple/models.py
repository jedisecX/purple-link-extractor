from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SourceRecord:
    id: int
    filename: str
    file_path: str | None
    file_size: int | None
    file_hash: str | None
    imported_at: str
    link_count: int
    status: str = "complete"


@dataclass
class DomainRecord:
    id: int
    hostname: str
    registered_domain: str | None
    first_seen: str
    last_seen: str
    link_count: int


@dataclass
class LinkRecord:
    id: int
    domain_id: int
    original_url: str
    normalized_url: str
    scheme: str | None
    hostname: str | None
    port: int | None
    path: str | None
    query: str | None
    fragment: str | None
    first_seen: str
    last_seen: str
    source_file: str | None
    source_row: int | None
    source_column: str | None
