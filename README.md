# Purple Link Extractor

Domain-aware URL librarian for large text and CSV corpora.

Extracts HTTP/HTTPS URLs from `.txt` and `.csv` files, normalizes and deduplicates them, classifies each URL by hostname and registrable domain (public-suffix aware), and stores everything in a portable SQLite database with full source provenance.

Pipeline: **DISCOVER → EXTRACT → NORMALIZE → CLASSIFY → STORE**

Not a crawler. It does not fetch URLs.

## Features

- Streaming import (line/row) — does not load entire files into RAM
- `.txt` and `.csv` (auto delimiter, quoted fields, all columns scanned)
- Files, directories, recursive scan
- Public-suffix domains via `tldextract` (`foo.example.co.uk` → `example.co.uk`)
- Keeps both `original_url` and `normalized_url`
- Dedupes on normalized form; tracks every source file via `link_sources`
- Crash-safe batched SQLite transactions + WAL + file-hash skip
- CLI: import, stats, domains, search, export (csv/json/per-domain directory)
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
purple --db links.db import ./input/ --recursive

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
- `links` — original + normalized URL, parsed parts, source hints
- `sources` — file path, size, SHA-256, import status, checkpoints
- `link_sources` — many sources per unique URL

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
  cli.py          CLI
  config.py       YAML + defaults
  database.py     SQLite schema + WAL
  extractor.py    TXT/CSV URL harvest
  normalizer.py   scheme/host/port/IDN
  domains.py      public-suffix split
  importer.py     streaming pipeline
  exporter.py     csv/json/domain dirs
  statistics.py   reports
examples/
  sample.txt
  sample.csv
```

## License

MIT
