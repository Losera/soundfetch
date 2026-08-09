#!/usr/bin/env python3
"""Benchmark live downloads through the installed ``soundfetch`` CLI.

Freesound and Internet Archive run by default. Video is opt-in with
``--video`` and requires the ``video`` extra. Every run gets a fresh output
folder so existing manifests and files cannot turn downloads into resume skips.

Examples:

    python scripts/benchmark_cli.py --limit 3 --query rain
    python scripts/benchmark_cli.py --limit 2 --video

Freesound searches require ``FREESOUND_API_KEY``. This script performs real
network requests and is intentionally separate from the offline test suite.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_SOURCES = ("freesound", "archive")
TABLE_COLUMNS = ("source", "files", "total_s", "avg_s", "p50", "p95", "bytes", "MB/s")


class CommandFailed(RuntimeError):
    """Raised when a benchmarked CLI command fails."""


def _cli_prefix() -> list[str]:
    executable = shutil.which("soundfetch")
    if executable:
        return [executable]
    # This still exercises Click's real entry point when running from a source
    # checkout that has not installed the console script.
    return [sys.executable, "-c", "from soundfetch.cli import main; main()"]


def _run(command: list[str], *, label: str) -> tuple[float, str]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        raise CommandFailed(f"{label} timed out after 300 seconds") from exc
    elapsed = time.monotonic() - started
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise CommandFailed(f"{label} exited {completed.returncode}: {detail}")
    return elapsed, completed.stdout


def _latest_records(path: Path) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (str(record.get("provider", "")), str(record.get("provider_id", "")))
            latest[key] = record
    return list(latest.values())


def _percentile(values: list[float], percentile: float) -> float:
    """Return a linearly interpolated percentile without a numeric dependency."""
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _summarize(source: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    downloaded = [record for record in records if record.get("status") == "downloaded"]
    timings = [float(record["elapsed_s"]) for record in downloaded if record.get("elapsed_s") is not None]
    total_bytes = sum(int(record.get("bytes") or 0) for record in downloaded)
    total_s = sum(timings)
    return {
        "source": source,
        "files": len(downloaded),
        "total_s": total_s,
        "avg_s": total_s / len(timings) if timings else 0.0,
        "p50": _percentile(timings, 0.50),
        "p95": _percentile(timings, 0.95),
        "bytes": total_bytes,
        "MB/s": (total_bytes / 1_048_576) / total_s if total_s else 0.0,
    }


def _benchmark_source(
    source: str,
    *,
    query: str,
    limit: int,
    output_dir: Path,
) -> tuple[dict[str, Any], float, float]:
    source_dir = output_dir / source
    source_dir.mkdir(parents=True)
    manifest = source_dir / "manifest.jsonl"
    prefix = _cli_prefix()

    search_s, search_stdout = _run(
        prefix
        + [
            source,
            "search",
            query,
            "--outdir",
            str(source_dir),
            "--max-results",
            str(limit),
            "--json",
        ],
        label=f"{source} search",
    )
    try:
        search_payload = json.loads(search_stdout)
    except json.JSONDecodeError as exc:
        raise CommandFailed(f"{source} search emitted invalid JSON: {search_stdout[:300]!r}") from exc
    if not search_payload.get("ok"):
        raise CommandFailed(f"{source} search returned an error payload: {search_payload}")

    download_command = prefix + [
        source,
        "download",
        "--manifest",
        str(manifest),
        "--outdir",
        str(source_dir),
        "--rate-delay",
        "0",
    ]
    if source == "freesound":
        download_command.extend(["--mode", "preview"])
    download_s, _ = _run(download_command, label=f"{source} download")

    records = _latest_records(manifest)
    errors = [record for record in records if record.get("status") == "error"]
    if errors:
        messages = "; ".join(str(record.get("error") or "unknown error") for record in errors)
        raise CommandFailed(f"{source} recorded {len(errors)} download error(s): {messages}")
    summary = _summarize(source, records)
    if summary["files"] != search_payload.get("count"):
        raise CommandFailed(
            f"{source} searched {search_payload.get('count')} files but downloaded "
            f"{summary['files']}"
        )
    return summary, search_s, download_s


def _print_table(rows: list[dict[str, Any]]) -> None:
    rendered: list[dict[str, str]] = []
    for row in rows:
        rendered.append(
            {
                "source": str(row["source"]),
                "files": str(row["files"]),
                "total_s": f"{row['total_s']:.3f}",
                "avg_s": f"{row['avg_s']:.3f}",
                "p50": f"{row['p50']:.3f}",
                "p95": f"{row['p95']:.3f}",
                "bytes": f"{row['bytes']:,}",
                "MB/s": f"{row['MB/s']:.3f}",
            }
        )
    widths = {
        column: max(len(column), *(len(row[column]) for row in rendered))
        for column in TABLE_COLUMNS
    }
    numeric = set(TABLE_COLUMNS) - {"source"}

    def line(row: dict[str, str]) -> str:
        return " | ".join(
            row[column].rjust(widths[column]) if column in numeric else row[column].ljust(widths[column])
            for column in TABLE_COLUMNS
        )

    print(line({column: column for column in TABLE_COLUMNS}))
    print("-+-".join("-" * widths[column] for column in TABLE_COLUMNS))
    for row in rendered:
        print(line(row))


def _default_output_dir() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"benchmarks/cli-{stamp}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=3, help="Files per source (default: %(default)s)")
    parser.add_argument("--query", default="rain", help="Search query (default: %(default)s)")
    parser.add_argument("--outdir", default=None, help="Fresh benchmark output directory")
    parser.add_argument("--video", action="store_true", help="Also benchmark the video provider")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be at least 1")

    output_dir = Path(args.outdir or _default_output_dir())
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error(f"output directory is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    sources = list(DEFAULT_SOURCES)
    if args.video:
        if importlib.util.find_spec("yt_dlp") is None:
            print('Skipping video: yt-dlp is not installed (pip install "soundfetch[video]").')
        else:
            sources.append("video")

    print(f"soundfetch CLI benchmark: query={args.query!r}, limit={args.limit}")
    print(f"output: {output_dir}\n")
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for source in sources:
        print(f"Benchmarking {source}...")
        try:
            row, search_s, download_s = _benchmark_source(
                source,
                query=args.query,
                limit=args.limit,
                output_dir=output_dir,
            )
        except (CommandFailed, OSError) as exc:
            failures.append(str(exc))
            print(f"  FAILED: {exc}")
            continue
        rows.append(row)
        print(
            f"  search wall={search_s:.3f}s; download wall={download_s:.3f}s; "
            f"files={row['files']}"
        )

    if rows:
        print()
        _print_table(rows)
    if failures:
        print("\nFailures:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
