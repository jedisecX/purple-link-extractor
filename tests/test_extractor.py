from purple.extractor import extract_from_text


def test_plain_urls():
    urls = extract_from_text("https://example.com http://example.org/a")
    assert {u.raw for u in urls} == {"https://example.com", "http://example.org/a"}


def test_embedded_and_punctuation():
    text = "Visit https://example.com/data, and also see https://www.example.gov/files/report.pdf."
    urls = extract_from_text(text)
    raws = [u.raw for u in urls]
    assert "https://example.com/data" in raws
    assert "https://www.example.gov/files/report.pdf" in raws


def test_multiple_per_line():
    urls = extract_from_text("https://a.com/x https://b.com/y")
    assert len(urls) == 2


def test_ignores_non_urls():
    assert extract_from_text("not a url example.com ftp://x.com") == []


def test_malformed():
    assert extract_from_text("https://") == []
