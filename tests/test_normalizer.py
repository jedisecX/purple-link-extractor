from purple.normalizer import normalize


def test_case_and_default_port():
    a = normalize("HTTPS://Example.COM:443/Test")
    b = normalize("https://example.com/Test")
    assert a.valid and b.valid
    assert a.normalized == b.normalized == "https://example.com/Test"


def test_http_default_port():
    n = normalize("http://example.com:80/a")
    assert n.normalized == "http://example.com/a"
    assert n.port is None


def test_keeps_query_and_fragment():
    n = normalize("https://example.com/a?q=1#frag")
    assert n.query == "q=1"
    assert n.fragment == "frag"


def test_rejects_other_schemes():
    n = normalize("ftp://example.com/a")
    assert not n.valid


def test_idn():
    n = normalize("https://xn--bcher-kva.example/path")
    assert n.valid
    assert n.hostname.endswith(".example")
