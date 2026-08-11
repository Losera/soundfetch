"""soundfetch dataset exports — build WebDataset shards and attribution
files from a soundfetch manifest.

Both functions consume ``manifest.jsonl`` (the dataset index written by
``soundfetch <provider> search`` / ``soundfetch <provider> download``) and
only consider records with ``status == "downloaded"`` and a ``local_file``
that exists on disk.

Heavy libraries (``webdataset``, ``soundfile``) are imported **inside**
``to_webdataset`` so the base ``soundfetch`` package never pulls them in::

    pip install "soundfetch[export]"  # pulls webdataset + soundfile

A HuggingFace-datasets exporter (``to_hf_dataset``) was attempted for the
0.3.0 beta and deliberately left out: it crashed on its own docstring
example against the installed ``datasets`` Audio feature (the encoded
``{"path": ..., "array": None}`` shape isn't valid input). See
``docs/deferred-work.md`` before rebuilding it.

Examples
--------
    import soundfetch

    # From a two-phase workflow: search → review → download → export
    refs = soundfetch.search("rain", provider="archive", license="cc0", max_results=200)
    soundfetch.save_search(refs, "out/manifest.jsonl")
    soundfetch.download(refs, dest_dir="out/")

    # WebDataset shards
    from soundfetch.export import to_webdataset
    shards = to_webdataset("out/manifest.jsonl", out_dir="shards/", shard_size=1000)

    # Attribution file for ML compliance
    from soundfetch.export import export_attribution
    export_attribution("out/manifest.jsonl")
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from .core.manifest import iter_latest

__all__ = ["to_webdataset", "export_attribution"]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _select_downloaded(
    manifest: str | Path,
    dest_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return enriched copies of every *downloaded* record in the manifest.

    Each returned dict contains the original record fields plus:

    * ``local_path`` — resolved absolute ``Path`` to the audio file.
    * ``author`` — extracted from metadata.
    * ``license_text`` — extracted from metadata.
    * ``duration`` — extracted from metadata.
    * ``samplerate`` — extracted from metadata.
    * ``gen_ai`` — extracted from metadata.

    Args:
        manifest: Path to the ``manifest.jsonl`` file.
        dest_dir: Base directory used to resolve relative ``local_file``
            values.  Defaults to the parent directory of *manifest*.

    Returns:
        A list of enriched record dicts, or an empty list when nothing
        matches.
    """
    manifest = Path(manifest)
    dest_dir = Path(dest_dir) if dest_dir is not None else manifest.parent

    results: list[dict[str, Any]] = []
    for record in iter_latest(manifest):
        if record.get("status") != "downloaded":
            continue
        local_file = record.get("local_file")
        if not local_file:
            continue

        local_path = (dest_dir / local_file).resolve()
        meta = record.get("metadata", {}) or {}

        enriched: dict[str, Any] = dict(record)
        enriched["local_path"] = local_path
        enriched["author"] = meta.get("username") or meta.get("author", "")
        enriched["license_text"] = meta.get("license", "")
        enriched["duration"] = meta.get("duration", 0)
        enriched["samplerate"] = meta.get("samplerate", 0)
        enriched["gen_ai"] = meta.get("gen_ai_preference")
        results.append(enriched)

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def to_webdataset(
    manifest: str | Path,
    dest_dir: str | Path | None = None,
    out_dir: str | Path = "",
    shard_size: int = 1000,
    compress: bool = True,
) -> list[Path]:
    """Write downloaded sounds as WebDataset tar shards.

    Each sample is stored as a group of files inside a tar archive:

    * The audio file itself.
    * ``{shard_index:05d}.json`` — a JSON metadata blob.
    * ``.txt`` — a human-readable attribution line.

    Shard files are numbered sequentially (``00000.tar.gz``, …).

    Args:
        manifest: Path to the ``manifest.jsonl`` file.
        dest_dir: Base directory for resolving relative ``local_file``
            values.  Defaults to the manifest's parent directory.
        out_dir: Directory to write the shard archives into.
        shard_size: Maximum number of samples per shard.
        compress: When ``True`` (default) shards use ``.tar.gz``
            compression; otherwise plain ``.tar``.

    Returns:
        A list of ``Path`` objects pointing to the created shard files.

    Raises:
        ValueError: If no downloaded records are found in the manifest.
    """
    records = _select_downloaded(manifest, dest_dir)
    if not records:
        raise ValueError("no downloaded sounds in manifest")

    import webdataset as wds  # lazy

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    suffix = ".tar.gz" if compress else ".tar"
    shard_paths: list[Path] = []

    shard_index = 0
    shard: Any = None

    for i, rec in enumerate(records):
        # Open a new shard when needed
        if i % shard_size == 0:
            if shard is not None:
                shard.close()
            shard_path = out_path / f"{shard_index:05d}{suffix}"
            shard = wds.TarWriter(str(shard_path))
            shard_paths.append(shard_path)
            shard_index += 1

        # Read audio bytes
        audio_bytes = Path(rec["local_path"]).read_bytes()

        # Derive a key from provider + provider_id
        key = f"{rec.get('provider', 'unknown')}_{rec.get('provider_id', '0')}"

        # Preserve the real audio extension (mp3/ogg/wav/flac/...) so shards
        # decode correctly — never hardcode one format.
        ext = (
            Path(rec["local_path"]).suffix.lstrip(".")
            or (rec.get("file_format") or "bin").lstrip(".")
        )

        # Build metadata dict (exclude large/unnecessary fields)
        meta = {
            "sound_id": rec.get("provider_id", ""),
            "name": rec.get("name", ""),
            "provider": rec.get("provider", ""),
            "license": rec["license_text"],
            "author": rec["author"],
            "duration": rec["duration"],
            "samplerate": rec["samplerate"],
            "gen_ai": rec["gen_ai"],
            "url": rec.get("url", ""),
        }

        attribution = (
            f"{rec['name']} by {rec['author']} — "
            f"{rec['license_text']} — {rec.get('url', '')}"
        )

        shard.write({
            "__key__": key,
            ext: audio_bytes,
            "json": meta,
            "txt": attribution,
        })

    if shard is not None:
        shard.close()

    return shard_paths


def export_attribution(
    manifest: str | Path,
    dest_dir: str | Path | None = None,
    out_path: str | Path | None = None,
) -> Path:
    """Write a Markdown attribution file for all downloaded sounds.

    The file follows a simple structure listing each sound with its
    provider, license, author, gen-AI preference, source URL, and local
    file path.  This is useful for ML compliance and reproducibility.

    Args:
        manifest: Path to the ``manifest.jsonl`` file.
        dest_dir: Base directory for resolving relative ``local_file``
            values.  Defaults to the manifest's parent directory.
        out_path: Full path for the output file.  Defaults to
            ``ATTRIBUTION.md`` in the same directory as *manifest*.

    Returns:
        The ``Path`` of the written attribution file.
    """
    records = _select_downloaded(manifest, dest_dir)

    if out_path is None:
        base = Path(dest_dir) if dest_dir is not None else Path(manifest).parent
        out_path = base / "ATTRIBUTION.md"
    else:
        out_path = Path(out_path)

    today = datetime.date.today().isoformat()

    lines: list[str] = [
        "# Sound Attribution",
        "",
        f"Collected with soundfetch on {today}",
        "",
        "---",
        "",
    ]

    for rec in records:
        lines.append(f"## {rec.get('name', 'Untitled')} (#{rec.get('provider_id', '?')})")
        lines.append("")
        lines.append(f"- **Provider:** {rec.get('provider', '?')}")
        lines.append(f"- **License:** {rec['license_text'] or 'not specified'}")
        lines.append(f"- **Author:** {rec['author'] or 'not specified'}")
        lines.append(f"- **Gen-AI preference:** {rec['gen_ai'] or 'not specified'}")
        lines.append(f"- **Source:** {rec.get('url', '?')}")
        lines.append(f"- **File:** {rec.get('local_file', '?')}")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")

    return out_path
