from purple.domains import parse_domain


def test_simple():
    p = parse_domain("www.example.gov")
    assert p.hostname == "www.example.gov"
    assert p.registered_domain == "example.gov"
    assert p.subdomain == "www"


def test_co_uk():
    p = parse_domain("foo.example.co.uk")
    assert p.registered_domain == "example.co.uk"
    assert p.subdomain == "foo"


def test_sub():
    p = parse_domain("data.example.gov")
    assert p.registered_domain == "example.gov"
    assert p.hostname == "data.example.gov"
