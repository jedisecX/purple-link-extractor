# Purple Link Extractor

Domain-aware URL librarian for large text and CSV corpora.

Extracts HTTP/HTTPS URLs from `.txt` and `.csv` files, normalizes and deduplicates them, classifies each URL by hostname and registrable domain (public-suffix aware), and stores everything in a portable SQLite database with full source provenance.

Pipeline: **DISCOVER → EXTRACT → NORMALIZE → CLASSIFY → STORE**

Not a document crawler. File import never fetches URLs. Optional dork harvest queries Yahoo/Bing for result links only.

## Features

- Streaming import (line/row) — does not load entire files into RAM
- `.txt` and `.csv` (auto delimiter, quoted fields, all columns scanned)
- Files, directories, recursive scan
- Public-suffix domains via `tldextract` (`foo.example.co.uk` → `example.co.uk`)
- Keeps both `original_url` and `normalized_url`
- Dedupes on normalized form; tracks every source file via `link_sources`
- Crash-safe batched SQLite transactions + WAL + file-hash skip
- CLI: import, stats, domains, search, export (csv/json/per-domain directory)
- Control Center UI (`purple serve`) — glass cyberpunk library over the same SQLite
- Keyset pagination on `/api/urls` (`after` cursor + `has_more` / `next`)
- Virtualized search/domain tables for million-row corpora
- Harvest queue as a handoff list only — no auto-download
- Dork harvest (Yahoo + Bing) with rotating headers and Yahoo `/RU=` unwrap
- Harvest writes into the same SQLite; csv/txt only on export
- YAML config; CLI flags override
- Parameterized SQL only. Input treated as untrusted.

## Install

Python 3.12+

```bash
git clone https://github.com/jedisecX/purple-link-extractor.git
cd purple-link-extractor
python3 -m pip install -r requirements.txt
python3 -m pip install -e .
```

Or run without install:

```bash
PYTHONPATH=. python3 -m purple --help
```

## Usage

```bash
purple import links.txt
purple import data.csv
purple import ./input/ --recursive
purple import ./input/ --db links.db

purple stats
purple domains
purple domain example.gov
purple search "example.gov"

purple export-domain example.gov
purple export csv
purple export json
purple export dir --out ./output
```

`--db` belongs on the root command:

```bash
purple --db links.db import ./input/ --recursive
```

## Control Center

```bash
pip install -r requirements.txt
PYTHONPATH=. python3 -m purple --db purple.db serve --host 127.0.0.1 --port 8747
```

Open http://127.0.0.1:8747

The UI is a management layer over the existing SQLite librarian. It does not crawl URLs.

Search pages with `GET /api/urls?after=<id>&limit=80`. The virtual table requests `after=next` until `has_more` is false.

### Dork harvest

Queries Yahoo and Bing. Unwraps Yahoo `/RU=.../RK=` and Bing `/ck/a?u=a1...` wrappers. Rotates User-Agent / Accept-Language. Indexes hits into the existing `links` table (normalized_url unique — no second database, no duplicate rows). Does not download the documents. Files are written only by `purple export`.

```bash
purple harvest "site:cisa.gov filetype:pdf" --engine yahoo --engine bing --pages 8
purple export csv
```

## Config (`purple.yaml`)

```yaml
database: purple.db
import:
  recursive: false
  batch_size: 1000
  accepted_schemes:
    - http
    - https
output:
  directory: ./output
logging:
  level: INFO
```

## Database

Self-contained SQLite. Core tables:

- `domains` — hostname, registered_domain, first/last seen, link_count
- `links` — original + normalized URL, parsed parts, source hints, status
- `sources` — file path, size, SHA-256, import status, checkpoints
- `link_sources` — many sources per unique URL
- `harvest_queue` — handoff list for a downstream harvester
- `activity` / `saved_searches` — Control Center metadata

## Tests

```bash
python3 -m pytest -q
```

## Benchmark

```bash
PYTHONPATH=. python3 scripts/benchmark.py --n 1000000
```

## Layout

```
purple/
  cli.py              CLI
  config.py           YAML + defaults
  database.py         SQLite schema + WAL
  extractor.py        TXT/CSV URL harvest
  normalizer.py       scheme/host/port/IDN
  domains.py          public-suffix split
  importer.py         streaming pipeline + harvest ingest
  harvester.py        Yahoo/Bing dork discovery
  exporter.py         csv/json/domain dirs
  statistics.py       reports
  api/app.py          FastAPI Control Center
  services/library.py library queries + keyset pages
frontend/             Control Center UI
examples/
  sample.txt
  sample.csv
```

## License

MIT
