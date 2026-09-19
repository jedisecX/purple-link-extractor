from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

# Conservative HTTP(S) URL finder. Captures scheme through the last
# non-whitespace / non-delimiter character; trailing prose punctuation
# is stripped in a second pass.
URL_RE = re.compile(
    r"""(?xi)
    (?P<url>
        https?://
        (?:
            [^\s<>"'{}|\\^`\[\]<>]
        )+
    )
    """
)

TRAILING_PUNCT = ".,;:!?)]}'\"\u201d\u2019\u00bb"
MAX_URL_LEN = 8192


@dataclass(frozen=True)
class ExtractedURL:
    raw: str
    source_file: str
    source_row: int | None = None
    source_column: str | None = None


def _strip_wrapping(token: str) -> str:
    token = token.strip()
    while token and token[0] in "([{<'\"\u201c\u2018\u00ab":
        token = token[1:]
    while token and token[-1] in TRAILING_PUNCT:
        # Keep trailing slash, keep balanced query chars
        if token[-1] == ")" and token.count("(") >= token.count(")"):
            break
        if token[-1] == "]" and token.count("[") >= token.count("]"):
            break
        token = token[:-1]
    return token.rstrip("/") if token.endswith(")/") else token


def extract_from_text(text: str, source_file: str = "", source_row: int | None = None, source_column: str | None = None) -> list[ExtractedURL]:
    found: list[ExtractedURL] = []
    for match in URL_RE.finditer(text or ""):
        raw = _strip_wrapping(match.group("url"))
        if not raw or len(raw) > MAX_URL_LEN:
            continue
        if "://" not in raw:
            continue
        found.append(
            ExtractedURL(
                raw=raw,
                source_file=source_file,
                source_row=source_row,
                source_column=source_column,
            )
        )
    return found


def iter_txt_urls(path: Path) -> Iterator[ExtractedURL]:
    name = path.name
    with path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        for i, line in enumerate(fh, start=1):
            yield from extract_from_text(line, source_file=name, source_row=i)


def _sniff_dialect(sample: str) -> csv.Dialect:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        class Fallback(csv.Dialect):
            delimiter = ","
            quotechar = '"'
            doublequote = True
            skipinitialspace = True
            lineterminator = "\n"
            quoting = csv.QUOTE_MINIMAL

        return Fallback()


def iter_csv_urls(path: Path) -> Iterator[ExtractedURL]:
    name = path.name
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        sample = fh.read(65536)
        fh.seek(0)
        dialect = _sniff_dialect(sample)
        reader = csv.reader(fh, dialect)
        headers: list[str] | None = None
        try:
            has_header = csv.Sniffer().has_header(sample)
        except csv.Error:
            has_header = False
        for row_num, row in enumerate(reader, start=1):
            if row_num == 1 and has_header:
                headers = [str(c) if c is not None else f"col{i}" for i, c in enumerate(row)]
            for col_idx, cell in enumerate(row):
                if not cell:
                    continue
                col_name = None
                if headers and col_idx < len(headers):
                    col_name = headers[col_idx]
                else:
                    col_name = f"col{col_idx}"
                yield from extract_from_text(
                    str(cell),
                    source_file=name,
                    source_row=row_num,
                    source_column=col_name,
                )


def iter_file_urls(path: Path) -> Iterator[ExtractedURL]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        yield from iter_csv_urls(path)
    else:
        yield from iter_txt_urls(path)
