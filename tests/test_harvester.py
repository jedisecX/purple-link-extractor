from urllib.parse import quote

from purple.harvester import unwrap_bing, unwrap_yahoo, urls_from_html, SearchHarvester
from purple.importer import Importer


def test_unwrap_yahoo_ru():
    dest = "https://www.cisa.gov/sites/default/files/publications/guide.pdf"
    wrapped = f"https://r.search.yahoo.com/YLT=abc/RU={quote(dest, safe='')}/RK=2/RS=xyz"
    assert unwrap_yahoo(wrapped) == dest


def test_unwrap_yahoo_skips_search_hosts():
    assert unwrap_yahoo("https://search.yahoo.com/search?p=test") is None


def test_unwrap_bing_ck():
    dest = "https://www.fbi.gov/file-repository/report.pdf"
    import base64

    token = "a1" + base64.urlsafe_b64encode(dest.encode()).decode().rstrip("=")
    wrapped = f"https://www.bing.com/ck/a?!&&p=abc&u={token}"
    assert unwrap_bing(wrapped) == dest


def test_urls_from_yahoo_html():
    dest = "https://www.cisa.gov/news.pdf"
    html = f'<html><a href="https://r.search.yahoo.com/x/RU={quote(dest, safe="")}/RK=2/RS=z">doc</a></html>'
    urls = urls_from_html(html, "yahoo")
    assert dest in urls


def test_harvest_uses_injected_fetch():
    dest = "https://example.gov/a.pdf"

    def fake_fetch(url, params, headers, timeout):
        assert "User-Agent" in headers
        if "yahoo.com" in url:
            return f'<a href="https://r.search.yahoo.com/x/RU={quote(dest, safe="")}/RK=2/RS=z">x</a>'
        return f'<a href="{dest}">x</a>'

    h = SearchHarvester(delay=0, fetch_fn=fake_fetch)
    stats = h.harvest("site:example.gov filetype:pdf", engines=["yahoo", "bing"], pages=1)
    assert dest in stats.urls
    assert stats.discovered == 1


def test_ingest_dedupes_against_existing_db(tmp_path):
    src = tmp_path / "seed.txt"
    src.write_text("https://example.gov/report.pdf\n", encoding="utf-8")
    db = tmp_path / "p.db"
    Importer(db).import_path(src)
    stats = Importer(db).ingest_urls(
        ["https://example.gov/report.pdf", "https://example.gov/new.pdf"],
        source_name="harvest:yahoo:test",
        label="harvest",
    )
    assert stats.duplicates == 1
    assert stats.urls_discovered == 2
    assert stats.unique_urls == 2
