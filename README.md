# Purple Link Extractor

Domain-aware URL librarian for large text and CSV corpora.

Extracts HTTP/HTTPS URLs from `.txt` and `.csv` files, normalizes and deduplicates them, classifies each URL by hostname and registrable domain (public-suffix aware), and stores everything in a portable SQLite database with full source provenance.

Pipeline: **DISCOVER → EXTRACT → NORMALIZE → CLASSIFY → STORE**

Not a crawler. It does not fetch URLs.

## Features

- Streaming import (line/row)
- TXT/CSV, recursive directories
- Public-suffix domains via tldextract
- original_url + normalized_url, link_sources provenance
- Crash-safe batched SQLite WAL imports
- CLI plus Control Center (`purple serve`)
- Keyset pagination on /api/urls
- Virtualized search/domain tables

## Control Center

```bash
pip install -r requirements.txt
PYTHONPATH=. python3 -m purple --db purple.db serve --host 127.0.0.1 --port 8747
```

Open http://127.0.0.1:8747

## CLI

```bash
purple --db links.db import ./input/ --recursive
purple stats
purple domains
purple search "example.gov"
purple export csv
```

## License

MIT
