from __future__ import annotations

from dataclasses import dataclass

import tldextract

_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=())


@dataclass(frozen=True)
class DomainParts:
    hostname: str
    subdomain: str
    registered_domain: str
    suffix: str


def parse_domain(hostname: str) -> DomainParts:
    host = (hostname or "").lower().strip(".")
    ext = _EXTRACTOR(host)
    registered = (
        getattr(ext, "top_domain_under_public_suffix", None)
        or getattr(ext, "registered_domain", None)
        or host
    )
    subdomain = ext.subdomain or ""
    suffix = ext.suffix or ""
    return DomainParts(
        hostname=host,
        subdomain=subdomain,
        registered_domain=registered,
        suffix=suffix,
    )
