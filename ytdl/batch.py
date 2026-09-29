"""Parsing of batch files (one line per download).

Each non-empty, non-comment line is either:

    "title with, commas",https://youtube.com/watch?v=xxxx
    Simple Title,https://youtube.com/watch?v=xxxx
    https://youtube.com/watch?v=xxxx

i.e. an optional title (quoted when it contains commas) followed by the URL, or
just the URL on its own. Titles are used verbatim as the output file name; a
line without a title falls back to yt-dlp's default naming.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class BatchEntry:
    url: str
    title: Optional[str] = None


def _looks_like_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def parse_batch_file(path: Path) -> list[BatchEntry]:
    """Parse a batch file into a list of :class:`BatchEntry` (order preserved)."""
    entries: list[BatchEntry] = []
    text = Path(path).read_text(encoding="utf-8")

    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # csv handles quoted titles containing commas/parentheses.
        fields = next(csv.reader([raw]))
        fields = [f.strip() for f in fields]

        if len(fields) >= 2:
            title, url = fields[0], fields[1]
            title = title or None
        else:
            title, url = None, fields[0]

        if not _looks_like_url(url):
            print(f"[ytdl] batch: skipping line {lineno} (not a URL): {stripped}",
                  file=sys.stderr)
            continue

        entries.append(BatchEntry(url=url, title=title))

    return entries
