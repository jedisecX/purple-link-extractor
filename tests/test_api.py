from pathlib import Path

from fastapi.testclient import TestClient

from purple.api.app import create_app
from purple.importer import Importer


def _seed(tmp_path: Path) -> Path:
    src = tmp_path / "a.txt"
    src.write_text("https://example.gov/report.pdf\nhttps://data.example.gov/x.csv\n", encoding="utf-8")
    db = tmp_path / "p.db"
    Importer(db).import_path(src)
    return db


def test_stats_and_search(tmp_path):
    db = _seed(tmp_path)
    client = TestClient(create_app(db))
    s = client.get("/api/stats").json()
    assert s["total_urls"] == 2
    assert s["total_domains"] >= 2
    urls = client.get("/api/urls", params={"q": "example.gov", "extension": "pdf"}).json()
    assert urls["total"] == 1
    detail = client.get(f"/api/urls/{urls['items'][0]['id']}").json()
    assert detail["hostname"].endswith("example.gov")
    assert detail["source_history"]


def test_keyset_pagination(tmp_path):
    src = tmp_path / "many.txt"
    src.write_text("\n".join(f"https://example.gov/item/{i}" for i in range(25)), encoding="utf-8")
    db = tmp_path / "p.db"
    Importer(db).import_path(src)
    client = TestClient(create_app(db))
    page1 = client.get("/api/urls", params={"limit": 10, "include_total": True}).json()
    assert len(page1["items"]) == 10
    assert page1["has_more"] is True
    assert page1["next"] == page1["items"][-1]["id"]
    page2 = client.get("/api/urls", params={"limit": 10, "after": page1["next"], "include_total": False}).json()
    assert len(page2["items"]) == 10
    ids1 = {r["id"] for r in page1["items"]}
    ids2 = {r["id"] for r in page2["items"]}
    assert not ids1 & ids2
    assert page2["items"][0]["id"] < page1["items"][-1]["id"]


def test_queue(tmp_path):
    db = _seed(tmp_path)
    client = TestClient(create_app(db))
    urls = client.get("/api/urls").json()["items"]
    r = client.post("/api/queue", json={"link_ids": [urls[0]["id"]], "priority": "HIGH"})
    assert r.json()["added"] == 1
    q = client.get("/api/queue").json()
    assert q["total"] == 1
    client.post("/api/queue/clear")
    assert client.get("/api/queue").json()["total"] == 0
