"""Read-only health summaries for Soundfetch manifests."""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


def build_manifest_report(
    manifest: str | Path,
    *,
    dest_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Summarize the effective records in an append-only JSONL manifest.

    Records use the manifest's established last-record-wins identity. Invalid
    JSON lines and non-object JSON values are counted instead of aborting the
    report, matching the readers' tolerance for an interrupted trailing write.
    """
    manifest_path = Path(manifest)
    resolved_dest = (
        Path(dest_dir).resolve()
        if dest_dir is not None
        else manifest_path.parent.resolve()
    )

    valid_records = 0
    invalid_records = 0
    latest: dict[tuple[str, str], dict[str, Any]] = {}

    with manifest_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                invalid_records += 1
                continue
            if not isinstance(record, dict):
                invalid_records += 1
                continue
            valid_records += 1
            key = (
                str(record.get("provider", "")),
                str(record.get("provider_id", "")),
            )
            latest[key] = record

    status_counts: Counter[str] = Counter()
    provider_counts: Counter[str] = Counter()
    license_counts: Counter[str] = Counter()
    missing_license = 0
    missing_source_url = 0

    downloaded = 0
    downloaded_bytes = 0
    duration_seconds = 0.0
    duration_known = 0
    missing_local_files = 0
    missing_checksums = 0

    for record in latest.values():
        status = _label(record.get("status"), "unknown")
        provider = _label(record.get("provider"), "unknown")
        metadata = record.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        license_value = _license(metadata)

        status_counts[status] += 1
        provider_counts[provider] += 1
        license_counts[license_value or "missing"] += 1
        if license_value is None:
            missing_license += 1
        if not _nonempty(record.get("url")):
            missing_source_url += 1

        if status != "downloaded":
            continue
        downloaded += 1
        downloaded_bytes += int(_number(record.get("bytes")) or 0)

        duration = _duration_seconds(metadata)
        if duration is not None:
            duration_seconds += duration
            duration_known += 1

        if not _local_file_exists(record.get("local_file"), resolved_dest):
            missing_local_files += 1
        if not _nonempty(record.get("checksum")):
            missing_checksums += 1

    effective = len(latest)
    return {
        "records": {
            "valid": valid_records,
            "invalid": invalid_records,
            "effective": effective,
            "superseded": valid_records - effective,
        },
        "status_counts": _sorted_counts(status_counts),
        "provider_counts": _sorted_counts(provider_counts),
        "license_counts": _sorted_counts(license_counts),
        "downloads": {
            "count": downloaded,
            "bytes": downloaded_bytes,
            "duration_seconds": round(duration_seconds, 3),
            "duration_known": duration_known,
            "duration_unknown": downloaded - duration_known,
            "missing_local_files": missing_local_files,
            "missing_checksums": missing_checksums,
        },
        "provenance": {
            "missing_license": missing_license,
            "missing_source_url": missing_source_url,
        },
    }


def _sorted_counts(counts: Counter[str]) -> dict[str, int]:
    return dict(sorted(counts.items()))


def _label(value: Any, default: str) -> str:
    return str(value).strip() if _nonempty(value) else default


def _nonempty(value: Any) -> bool:
    return value is not None and bool(str(value).strip())


def _license(metadata: dict[str, Any]) -> str | None:
    for key in ("license", "license_url", "licenseurl"):
        value = metadata.get(key)
        if _nonempty(value):
            return str(value).strip()
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return number


def _duration_seconds(metadata: dict[str, Any]) -> float | None:
    duration = _number(metadata.get("duration"))
    if duration is not None:
        return duration
    duration_ms = _number(metadata.get("duration_ms"))
    return duration_ms / 1000 if duration_ms is not None else None


def _local_file_exists(value: Any, dest_dir: Path) -> bool:
    if not _nonempty(value):
        return False
    local_path = (dest_dir / str(value)).resolve()
    return local_path.is_relative_to(dest_dir) and local_path.is_file()
