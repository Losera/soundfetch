"""Search + download loops shared by all providers.

Pagination, checkpointing, resume and manifest writes live here so a provider
only implements search()/download(). This is what makes the multi-source
platform real: a new source plugs in with zero core changes.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .downloader import DownloadError
from .manifest import append_record, latest_by_sound, read_records
from .model import DownloadResult, SearchPage, SearchParams, SoundRef
from .names import unique_path
from .provider import Provider

log = logging.getLogger(__name__)


def search_all(
    provider: Provider,
    params: SearchParams,
    *,
    on_page: Callable[[SearchPage, int], None] | None = None,
) -> list[SoundRef]:
    """Page through a provider's search until max_results or no more pages.

    The page counter is passed to the provider via SearchParams.extra["page"]
    (1-indexed). A fresh SearchParams is built per page so params is never
    mutated by the loop.
    """
    collected: list[SoundRef] = []
    page = 0
    while True:
        page += 1
        page_params = replace(params, extra={**params.extra, "page": page})
        result: SearchPage = provider.search(page_params, progress=None)
        collected.extend(result.results)
        if on_page:
            on_page(result, page)
        if params.max_results is not None and len(collected) >= params.max_results:
            collected = collected[: params.max_results]
            break
        if not result.has_more:
            break
    return collected


def write_search_records(manifest: Path, refs: list[SoundRef]) -> None:
    """Write one manifest record per sound found (status: 'listed')."""
    for ref in refs:
        record = ref_record(ref)
        record.update(
            {
                "status": "listed",
                "error": None,
            }
        )
        append_record(manifest, record)


def ref_record(ref: SoundRef) -> dict:
    """The manifest envelope for a SoundRef (before download status)."""
    return {
        "provider": ref.provider,
        "provider_id": ref.provider_id,
        "name": ref.name,
        "url": ref.url,
        "file_format": ref.file_format,
        "checksum": ref.checksum,
        "download_url": ref.download_url,
        "metadata": ref.metadata,
    }


def download_refs(
    provider: Provider,
    refs: list[SoundRef],
    dest_dir: Path,
    manifest: Path,
    *,
    resume: bool = True,
    overwrite: bool = False,
    fail_fast: bool = False,
    rate_delay: float = 0.0,
) -> list[DownloadResult]:
    """Download a list of sounds, checkpointing each to the manifest.

    With resume=True (default), sounds already marked 'downloaded' in the
    manifest whose local file still exists are skipped. Each attempt appends
    its own record, so an interrupted run picks up where it left off.
    """
    import time

    dest_dir.mkdir(parents=True, exist_ok=True)
    results: list[DownloadResult] = []

    if resume:
        done: dict[tuple[str, str], str] = {
            (r.get("provider", ""), str(r.get("provider_id", ""))): r.get("local_file", "")
            for r in latest_by_sound(read_records(manifest)).values()
            if r.get("status") == "downloaded" and r.get("local_file")
        }
    else:
        done = {}

    taken: set[str] = set()
    for idx, ref in enumerate(refs):
        key = (ref.provider, ref.provider_id)
        if not overwrite and key in done and (dest_dir / done[key]).exists():
            log.info("skip %s/%s (already downloaded)", ref.provider, ref.provider_id)
            results.append(DownloadResult(dest_dir / done[key], status="skipped"))
            continue

        # Name collision handling: unique within this run + on disk.
        stem = _safe_stem(ref)
        ext = (ref.file_format or "bin").lstrip(".")
        target = unique_path(dest_dir, stem, ext, taken=taken)
        taken.add(target.name)

        try:
            if idx > 0 and rate_delay > 0:
                time.sleep(rate_delay)
            result = provider.download(ref, dest_dir, target=target)
            record = ref_record(ref)
            record.update(
                {
                    "status": "downloaded",
                    "local_file": target.name,
                    "downloaded_at": _now(),
                    "bytes": result.bytes,
                    "checksum": result.checksum or ref.checksum,
                    "error": None,
                }
            )
            append_record(manifest, record)
            results.append(result)
            log.info("downloaded %s -> %s", ref.provider_id, target.name)
        except DownloadError as exc:
            record = ref_record(ref)
            record.update(
                {
                    "status": "error",
                    "local_file": None,
                    "error": str(exc),
                }
            )
            append_record(manifest, record)
            results.append(DownloadResult(local_path=target, bytes=0, status="error", error=str(exc)))
            log.error("failed %s/%s: %s", ref.provider, ref.provider_id, exc)
            if fail_fast:
                raise
    return results


def _safe_stem(ref: SoundRef) -> str:
    from .names import sanitize_stem

    return sanitize_stem(ref.name, f"sound-{ref.provider_id}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
