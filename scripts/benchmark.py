#!/usr/bin/env python3
"""Generate a synthetic 1,000,000-URL corpus and time the importer."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from purple.importer import Importer
from purple.statistics import print_import_stats


DOMAINS = [
    "example.gov",
    "data.gov",
    "state.la.us",
    "nasa.gov",
    "epa.gov",
    "example.com",
    "example.org",
    "foo.example.co.uk",
]


def generate(path: Path, n: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for i in range(n):
            host = DOMAINS[i % len(DOMAINS)]
            fh.write(f"https://{host}/item/{i}?q={i % 97}\n")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=1_000_000)
    p.add_argument("--out", default="bench_urls.txt")
    p.add_argument("--db", default="bench.db")
    args = p.parse_args()
    out = Path(args.out)
    if not out.exists() or out.stat().st_size == 0:
        print(f"Generating {args.n:,} URLs -> {out}")
        t0 = time.perf_counter()
        generate(out, args.n)
        print(f"Wrote in {time.perf_counter()-t0:.1f}s")
    db = Path(args.db)
    if db.exists():
        db.unlink()
    stats = Importer(db, batch_size=5000).import_path(out)
    print_import_stats(stats, db)


if __name__ == "__main__":
    main()
