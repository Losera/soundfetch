"""Append-only JSONL manifest — search output, checkpoint, resume log, dataset index.

One JSON object per line. The effective record for a sound is the last line
with a given (provider, provider_id), so re-searching or re-downloading never
rewrites the file: it just appends a newer line.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Iterator


def append_record(path: Path, record: dict[str, Any]) -> None:
    """Append one record as a JSON line (creating the file if needed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_records(path: Path) -> list[dict[str, Any]]:
    """Read every line; tolerate empty/missing files."""
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                # A torn last line from an interrupted append; ignore.
                continue
    return records


def latest_by_sound(records: Iterable[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Last-wins per (provider, provider_id)."""
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        key = (record.get("provider", ""), str(record.get("provider_id", "")))
        latest[key] = record
    return latest


def iter_latest(path: Path) -> Iterator[dict[str, Any]]:
    """Yield the effective (latest) record for each sound in the manifest."""
    yield from latest_by_sound(read_records(path)).values()
