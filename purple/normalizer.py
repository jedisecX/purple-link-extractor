from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import idna


@dataclass(frozen=True)
class NormalizedURL:
    original: str
    normalized: str
    scheme: str
    hostname: str
    port: int | None
    path: str
    query: str
    fragment: str
    valid: bool
    reason: str | None = None


def _idna_host(host: str) -> str:
    host = host.strip(".").lower()
    if not host:
        return host
    try:
        if host.startswith("xn--") or ".xn--" in host:
            host = idna.decode(host)
        return idna.encode(host).decode("ascii")
    except (idna.IDNAError, UnicodeError):
        return host.lower()


def normalize(original: str, accepted_schemes: list[str] | None = None) -> NormalizedURL:
    accepted = {s.lower() for s in (accepted_schemes or ["http", "https"])}
    raw = (original or "").strip()
    if not raw:
        return NormalizedURL(original, "", "", "", None, "", "", "", False, "empty")

    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        return NormalizedURL(original, "", "", "", None, "", "", "", False, str(exc))

    scheme = (parts.scheme or "").lower()
    if scheme not in accepted:
        return NormalizedURL(original, raw, scheme, "", None, "", "", "", False, "scheme")

    hostname = parts.hostname
    if not hostname:
        return NormalizedURL(original, raw, scheme, "", None, "", "", "", False, "host")

    hostname = _idna_host(hostname)
    if not hostname or "." not in hostname and hostname not in {"localhost"}:
        if hostname not in {"localhost"}:
            if not _looks_like_host(hostname):
                return NormalizedURL(original, raw, scheme, hostname, None, "", "", "", False, "host")

    port = parts.port
    if port is not None:
        if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
            port = None

    path = parts.path or ""
    query = parts.query or ""
    fragment = parts.fragment or ""

    netloc = hostname
    if port is not None:
        netloc = f"{hostname}:{port}"
    if parts.username:
        userinfo = parts.username
        if parts.password is not None:
            userinfo = f"{parts.username}:{parts.password}"
        netloc = f"{userinfo}@{netloc}"

    normalized = urlunsplit((scheme, netloc, path, query, fragment))
    return NormalizedURL(
        original=original,
        normalized=normalized,
        scheme=scheme,
        hostname=hostname,
        port=port,
        path=path,
        query=query,
        fragment=fragment,
        valid=True,
    )


def _looks_like_host(host: str) -> bool:
    if not host:
        return False
    if all(c.isdigit() or c == "." for c in host):
        return True
    if ":" in host:
        return True
    return bool(host)
