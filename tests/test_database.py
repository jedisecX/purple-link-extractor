import sqlite3

from purple.database import get_db


def test_schema_and_fk(tmp_path):
    db = tmp_path / "t.db"
    with get_db(db) as conn:
        conn.execute(
            "INSERT INTO domains (hostname, registered_domain, first_seen, last_seen) "
            "VALUES ('example.com','example.com','t','t')"
        )
        conn.execute(
            "INSERT INTO links (domain_id, original_url, normalized_url, first_seen, last_seen) "
            "VALUES (1,'https://example.com','https://example.com','t','t')"
        )
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        assert n == 1
        raised = False
        try:
            conn.execute(
                "INSERT INTO links (domain_id, original_url, normalized_url, first_seen, last_seen) "
                "VALUES (1,'https://example.com/x','https://example.com','t','t')"
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raised = True
            conn.rollback()
        assert raised
        assert conn.execute("SELECT COUNT(*) FROM links").fetchone()[0] == 1
