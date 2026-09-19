from __future__ import annotations

import base64
import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import parse_qs, unquote, urlparse

from purple.extractor import ExtractedURL, URL_RE, _strip_wrapping

log = logging.getLogger("purple")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
]

ACCEPT_LANGS = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.8",
    "en-GB,en;q=0.9,en-US;q=0.8",
]

SEARCH_HOSTS = {
    "search.yahoo.com",
    "r.search.yahoo.com",
    "yahoo.com",
    "www.yahoo.com",
    "bing.com",
    "www.bing.com",
    "r.bing.com",
    "duckduckgo.com",
    "google.com",
    "www.google.com",
}

ENGINES = ("yahoo", "bing")

PRESETS = {
    "CISA": "site:cisa.gov filetype:pdf",
    "DHS": "site:dhs.gov filetype:pdf",
    "FBI": "site:fbi.gov filetype:pdf",
    "NSA": "site:nsa.gov filetype:pdf",
    "FEMA": "site:fema.gov filetype:pdf",
    "DoD": "site:defense.gov filetype:pdf",
    "Army": "site:army.mil filetype:pdf",
    "Navy": "site:navy.mil filetype:pdf",
    "Air Force": "site:af.mil filetype:pdf",
    "Marine Corps": "site:marines.mil filetype:pdf",
    "GAO": "site:gao.gov filetype:pdf",
    "Congress": "site:congress.gov filetype:pdf",
}

YAHOO_RU_RE = re.compile(r"/RU=([^/]+)/RK=", re.I)
HREF_RE = re.compile(r"""href\s*=\s*[\"']([^\"']+)[\"']""", re.I)


def rotating_headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": random.choice(ACCEPT_LANGS),
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
    }


def unwrap_yahoo(href: str) -> str | None:
    """Decode Yahoo outbound wrappers (/RU=.../RK=) back to the real URL."""
    if not href:
        return None
    raw = href.strip()
    if "/RU=" in raw:
        m = YAHOO_RU_RE.search(raw)
        if m:
            raw = unquote(m.group(1))
        else:
            q = raw.split("/RU=", 1)[1]
            raw = unquote(q.split("/RK=")[0].split("&")[0])
    parsed = urlparse(raw)
    if parsed.hostname and parsed.hostname.lower() in SEARCH_HOSTS:
        return None
    if parsed.scheme in {"http", "https"}:
        return raw
    return None


def unwrap_bing(href: str) -> str | None:
    """Decode Bing click-wrappers (/ck/a?...&u=a1...) back to the real URL."""
    if not href:
        return None
    raw = href.strip()
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if host in {"bing.com", "www.bing.com"} and "/ck/" in parsed.path:
        qs = parse_qs(parsed.query)
        token = (qs.get("u") or [None])[0]
        if token:
            decoded = _decode_bing_u(token)
            if decoded:
                raw = decoded
                parsed = urlparse(raw)
                host = (parsed.hostname or "").lower()
    if host in SEARCH_HOSTS:
        return None
    if parsed.scheme in {"http", "https"}:
        return raw
    return None


def _decode_bing_u(token: str) -> str | None:
    blob = token[2:] if token.startswith("a1") else token
    pad = "=" * (-len(blob) % 4)
    try:
        out = base64.urlsafe_b64decode(blob + pad).decode("utf-8", "ignore")
    except Exception:
        return None
    if out.startswith("http://") or out.startswith("https://"):
        return out
    return None


def unwrap_href(href: str, engine: str) -> str | None:
    if engine == "yahoo":
        return unwrap_yahoo(href)
    if engine == "bing":
        return unwrap_bing(href)
    url = href if href.startswith("http") else None
    if not url:
        return None
    host = (urlparse(url).hostname or "").lower()
    if host in SEARCH_HOSTS:
        return None
    return url


def extract_hrefs(html: str) -> list[str]:
    hrefs = HREF_RE.findall(html or "")
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html or "", "html.parser")
        for a in soup.find_all("a", href=True):
            hrefs.append(a["href"])
    except ImportError:
        pass
    return hrefs


def urls_from_html(html: str, engine: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for href in extract_hrefs(html):
        url = unwrap_href(href, engine)
        if url and url not in seen:
            seen.add(url)
            found.append(url)
    for match in URL_RE.finditer(html or ""):
        raw = _strip_wrapping(match.group("url"))
        url = unwrap_href(raw, engine)
        if url and url not in seen:
            seen.add(url)
            found.append(url)
    return found


def default_fetch(url: str, params: dict, headers: dict, timeout: float) -> str:
    import httpx

    with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
        r = client.get(url, params=params)
        r.raise_for_status()
        return r.text


FetchFn = Callable[[str, dict, dict, float], str]


@dataclass
class HarvestStats:
    dork: str
    engines: list[str]
    pages: int
    discovered: int = 0
    urls: list[str] = field(default_factory=list)
    pages_fetched: int = 0
    errors: int = 0
    elapsed: float = 0.0


class SearchHarvester:
    """Search-engine dork discovery. Does not download result documents."""

    def __init__(
        self,
        delay: float = 2.0,
        timeout: float = 20.0,
        fetch_fn: FetchFn | None = None,
        progress_cb=None,
    ):
        self.delay = max(0.0, float(delay))
        self.timeout = float(timeout)
        self.fetch_fn = fetch_fn or default_fetch
        self.progress_cb = progress_cb

    def harvest(
        self,
        dork: str,
        engines: list[str] | None = None,
        pages: int = 5,
    ) -> HarvestStats:
        query = (dork or "").strip()
        if not query:
            raise ValueError("dork is required")
        chosen = [e.lower() for e in (engines or ["yahoo", "bing"]) if e.lower() in ENGINES]
        if not chosen:
            chosen = ["yahoo"]
        pages = min(max(int(pages), 1), 20)
        stats = HarvestStats(dork=query, engines=chosen, pages=pages)
        started = time.perf_counter()
        seen: set[str] = set()

        for engine in chosen:
            for page in range(pages):
                url, params = _engine_request(engine, query, page)
                headers = rotating_headers()
                try:
                    html = self.fetch_fn(url, params, headers, self.timeout)
                    stats.pages_fetched += 1
                except Exception as exc:
                    stats.errors += 1
                    log.warning("harvest %s page %s failed: %s", engine, page + 1, exc)
                    self._emit(stats, engine, page + 1, "ERROR")
                    continue
                for item in urls_from_html(html, engine):
                    if item not in seen:
                        seen.add(item)
                        stats.urls.append(item)
                stats.discovered = len(stats.urls)
                self._emit(stats, engine, page + 1, "SEARCHING")
                if self.delay:
                    time.sleep(self.delay)

        stats.elapsed = time.perf_counter() - started
        return stats

    def _emit(self, stats: HarvestStats, engine: str, page: int, status: str) -> None:
        if not self.progress_cb:
            return
        self.progress_cb(
            {
                "status": status,
                "engine": engine,
                "page": page,
                "dork": stats.dork,
                "discovered": stats.discovered,
                "pages_fetched": stats.pages_fetched,
                "errors": stats.errors,
            }
        )


def _engine_request(engine: str, query: str, page: int) -> tuple[str, dict]:
    start = page * 10 + 1
    if engine == "bing":
        return "https://www.bing.com/search", {"q": query, "first": start}
    return "https://search.yahoo.com/search", {"p": query, "b": start}


def as_extracted(urls: list[str], source_name: str) -> list[ExtractedURL]:
    out = []
    for i, raw in enumerate(urls, 1):
        out.append(ExtractedURL(raw=raw, source_file=source_name, source_row=i, source_column="harvest"))
    return out
