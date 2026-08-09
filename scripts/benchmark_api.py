#!/usr/bin/env python3
"""Benchmark live downloads through the in-process ``soundfetch`` API.

Freesound and Internet Archive run by default. Video is opt-in with
``--video`` and requires the ``video`` extra. The script writes raw CSV/JSON
metrics plus four matplotlib figures to ``benchmarks/out-<timestamp>/``.

Install chart dependencies with ``pip install -e '.[bench]'``. Freesound
searches require ``FREESOUND_API_KEY``. This script performs real network
requests and is intentionally separate from the offline test suite.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import soundfetch

DEFAULT_SOURCES = ("freesound", "archive")
COLORS = ("#4C78A8", "#F58518", "#54A24B")


def _plot_dependencies():
    try:
        import matplotlib.pyplot as plt
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "benchmark charts require matplotlib and pandas; "
            "install them with `pip install -e '.[bench]'`"
        ) from exc
    return plt, pd


def _benchmark_source(
    source: str,
    *,
    query: str,
    limit: int,
    output_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    source_dir = output_dir / source
    source_dir.mkdir(parents=True)
    manifest = source_dir / "manifest.jsonl"

    started = time.monotonic()
    refs = soundfetch.search(query, provider=source, max_results=limit)
    search_s = time.monotonic() - started
    soundfetch.save_search(refs, manifest)

    started = time.monotonic()
    results = soundfetch.download(
        refs,
        dest_dir=source_dir,
        manifest=manifest,
        rate_delay=0,
    )
    download_wall_s = time.monotonic() - started
    failures = [result for result in results if result.status == "error"]
    if failures:
        messages = "; ".join(result.error or "unknown error" for result in failures)
        raise RuntimeError(f"{source} recorded {len(failures)} download error(s): {messages}")

    records = [
        record
        for record in soundfetch.iter_latest(manifest)
        if record.get("status") == "downloaded"
    ]
    if len(records) != len(refs):
        raise RuntimeError(f"{source} searched {len(refs)} files but downloaded {len(records)}")

    rows: list[dict[str, Any]] = []
    cumulative_s = 0.0
    cumulative_bytes = 0
    for record in records:
        elapsed_s = float(record.get("elapsed_s") or 0)
        size = int(record.get("bytes") or 0)
        cumulative_s += elapsed_s
        cumulative_bytes += size
        rows.append(
            {
                "provider": source,
                "provider_id": str(record.get("provider_id", "")),
                "name": str(record.get("name", "")),
                "bytes": size,
                "size_mb": size / 1_048_576,
                "started_at": record.get("started_at"),
                "elapsed_s": elapsed_s,
                "completion_s": cumulative_s,
                "cumulative_bytes": cumulative_bytes,
                "local_file": record.get("local_file"),
            }
        )

    total_s = sum(row["elapsed_s"] for row in rows)
    total_bytes = sum(row["bytes"] for row in rows)
    summary = {
        "source": source,
        "files": len(rows),
        "search_wall_s": search_s,
        "download_wall_s": download_wall_s,
        "timed_download_s": total_s,
        "bytes": total_bytes,
        "mb_per_s": (total_bytes / 1_048_576) / total_s if total_s else 0.0,
    }
    return rows, summary


def _configure_axes(ax, *, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_title(title, loc="left", fontweight="bold", pad=12)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", alpha=0.22, linewidth=0.8)
    ax.spines[["top", "right"]].set_visible(False)


def _save_figure(fig, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")


def _render_figures(frame, output_dir: Path, plt) -> None:
    providers = list(dict.fromkeys(frame["provider"].tolist()))
    palette = {provider: COLORS[index % len(COLORS)] for index, provider in enumerate(providers)}

    throughput = (
        frame.groupby("provider", sort=False)[["size_mb", "elapsed_s"]]
        .sum()
        .assign(mb_per_s=lambda grouped: grouped["size_mb"] / grouped["elapsed_s"])
    )
    fig, ax = plt.subplots(figsize=(8, 4.8))
    ax.bar(
        throughput.index,
        throughput["mb_per_s"],
        color=[palette[provider] for provider in throughput.index],
        width=0.64,
    )
    _configure_axes(ax, title="Download throughput by source", xlabel="Source", ylabel="Throughput (MB/s)")
    _save_figure(fig, output_dir / "throughput.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.8))
    for provider in providers:
        values = frame.loc[frame["provider"] == provider, "elapsed_s"]
        bins = max(1, min(12, len(values)))
        ax.hist(values, bins=bins, alpha=0.58, color=palette[provider], label=provider)
    _configure_axes(ax, title="Per-file download latency", xlabel="Download time (seconds)", ylabel="Files")
    ax.legend(frameon=False)
    _save_figure(fig, output_dir / "latency.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.8))
    for provider in providers:
        values = frame.loc[frame["provider"] == provider, "size_mb"]
        bins = max(1, min(12, len(values)))
        ax.hist(values, bins=bins, alpha=0.58, color=palette[provider], label=provider)
    _configure_axes(ax, title="Downloaded file sizes", xlabel="File size (MB)", ylabel="Files")
    ax.legend(frameon=False)
    _save_figure(fig, output_dir / "sizes.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.8))
    for provider in providers:
        group = frame.loc[frame["provider"] == provider]
        x = [0.0, *group["completion_s"].tolist()]
        y = [0.0, *(group["cumulative_bytes"] / 1_048_576).tolist()]
        ax.step(x, y, where="post", linewidth=2.2, color=palette[provider], label=provider)
    _configure_axes(
        ax,
        title="Cumulative download progress",
        xlabel="Download wall-clock (seconds)",
        ylabel="Cumulative data (MB)",
    )
    ax.legend(frameon=False)
    _save_figure(fig, output_dir / "progress.png")
    plt.close(fig)


def _default_output_dir() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"benchmarks/out-{stamp}"


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

    try:
        plt, pd = _plot_dependencies()
    except RuntimeError as exc:
        parser.error(str(exc))

    sources = list(DEFAULT_SOURCES)
    if args.video:
        if importlib.util.find_spec("yt_dlp") is None:
            print('Skipping video: yt-dlp is not installed (pip install "soundfetch[video]").')
        else:
            sources.append("video")

    print(f"soundfetch API benchmark: query={args.query!r}, limit={args.limit}")
    print(f"output: {output_dir}\n")
    rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    failures: list[str] = []
    for source in sources:
        print(f"Benchmarking {source}...")
        try:
            source_rows, summary = _benchmark_source(
                source,
                query=args.query,
                limit=args.limit,
                output_dir=output_dir,
            )
        except Exception as exc:
            failures.append(f"{source}: {exc}")
            print(f"  FAILED: {exc}")
            continue
        rows.extend(source_rows)
        summaries.append(summary)
        print(
            f"  files={summary['files']}; search wall={summary['search_wall_s']:.3f}s; "
            f"download wall={summary['download_wall_s']:.3f}s"
        )

    if rows:
        frame = pd.DataFrame(rows)
        frame.to_csv(output_dir / "metrics.csv", index=False)
        (output_dir / "summary.json").write_text(
            json.dumps(summaries, indent=2),
            encoding="utf-8",
        )
        _render_figures(frame, output_dir, plt)
        print("\nWrote metrics.csv, summary.json, and four PNG figures.")
    if failures:
        print("\nFailures:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
    return 1 if failures or not rows else 0


if __name__ == "__main__":
    raise SystemExit(main())
