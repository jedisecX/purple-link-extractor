from pathlib import Path

from purple.importer import Importer


def test_import_txt_and_dedupe(tmp_path):
    src = tmp_path / "a.txt"
    src.write_text(
        "Visit https://example.com/data\n"
        "and also see https://www.example.gov/files/report.pdf\n"
        "https://example.com/data\n"
        "HTTPS://Example.COM/data\n",
        encoding="utf-8",
    )
    db = tmp_path / "p.db"
    stats = Importer(db).import_path(src)
    assert stats.files_processed == 1
    assert stats.urls_discovered == 4
    assert stats.unique_urls == 2

    # second import of same file skipped
    stats2 = Importer(db).import_path(src)
    assert stats2.files_skipped == 1
    assert stats2.unique_urls == 2


def test_csv_all_fields(tmp_path):
    src = tmp_path / "b.csv"
    src.write_text(
        "name,url,notes\n"
        "a,https://data.example.gov/c.csv,see also https://example.gov/b.pdf\n",
        encoding="utf-8",
    )
    db = tmp_path / "p.db"
    stats = Importer(db).import_path(src)
    assert stats.unique_urls == 2
