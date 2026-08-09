"""Search + download loops shared by all providers.

Pagination, checkpointing, resume and manifest writes live here so a provider
only implements search()/download(). This is what makes the multi-source
platform real: a new source plugs in with zero core changes.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .downloader import DownloadError
from .manifest import append_record
from .model import DownloadResult, SearchPage, SearchParams, SoundRef
from .names import unique_path
from .provider import Provider

log = logging.getLogger(__name__)


def _attach_limiter(provider: Provider, pacing, rate_delay: float):
    """Attach (once) a shared rate-limiter to a provider and return it.

    Priority: an already-attached limiter (so search + download phases of one
    run share a single bucket), then an explicit ``Pacing`` bucket, then a
    bucket derived from the legacy ``rate_delay`` (``1/rate_delay`` req/s,
    capacity 1 — reproduces the old sleep-between-downloads behavior exactly).
    Returns None when unpaced.
    """
    existing = getattr(provider, "rate_limiter", None)
    if existing is not None:
        return existing
    if pacing is not None:
        limiter = pacing.limiter(provider.name)
    elif rate_delay and rate_delay > 0:
        from .pacing import Pacing

        limiter = Pacing(rates={provider.name: 1.0 / rate_delay}).limiter(provider.name)
    else:
        return None
    try:
        provider.rate_limiter = limiter  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        return None
    return limiter


def search_all(
    provider: Provider,
    params: SearchParams,
    *,
    on_page: Callable[[SearchPage, int], None] | None = None,
    pacing=None,
) -> list[SoundRef]:
    """Page through a provider's search until max_results or no more pages.

    The page counter is passed to the provider via SearchParams.extra["page"]
    (1-indexed). A fresh SearchParams is built per page so params is never
    mutated by the loop. ``pacing`` (a core.pacing.Pacing) attaches a shared
    rate-limiter to the provider so pagination honors the rate ceiling.
    """
    if pacing is not None:
        _attach_limiter(provider, pacing, 0.0)
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
    workers: int = 1,
    pacing=None,
) -> list[DownloadResult]:
    """Download a list of sounds, checkpointing each to the manifest.

    With resume=True (default), sounds already marked 'downloaded' in the
    manifest whose local file still exists are skipped. Each attempt appends
    its own record, so an interrupted run picks up where it left off.

    ``workers > 1`` downloads in parallel through a bounded pool (order of
    results matches ``refs``). Pacing comes from ``pacing`` (a
    core.pacing.Pacing) or, for the legacy ``--rate-delay`` path, a bucket
    derived from ``rate_delay``; either way the bucket is shared across every
    request this provider makes, so parallel workers still stay under the
    provider's rate ceiling.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)

    done: dict[tuple[str, str], str] = {}
    if resume:
        done = _resume_done(manifest)

    workers = max(1, int(workers or 1))
    if workers > 1:
        # Parallel path: attach a shared bucket so all workers stay under the
        # rate ceiling (plain ``time.sleep`` can't pace across threads).
        _attach_limiter(provider, pacing, rate_delay)
        return _download_threaded(
            provider, refs, dest_dir, manifest,
            done=done, overwrite=overwrite, fail_fast=fail_fast, workers=workers,
        )

    # Sequential path: legacy ``rate_delay`` uses a plain sleep between
    # downloads (preserves the old ``[0.5, 0.5]`` test contract exactly).
    # An explicit ``pacing`` object still uses the token bucket for proper
    # rate-limiting that accounts for elapsed download time.
    if pacing is not None:
        _attach_limiter(provider, pacing, 0.0)

    results: list[DownloadResult] = []
    taken: set[str] = set()
    for idx, ref in enumerate(refs):
        if pacing is None and rate_delay > 0 and idx > 0:
            time.sleep(rate_delay)
        results.append(
            _attempt_download(
                provider, ref, dest_dir, manifest,
                done=done, taken=taken, overwrite=overwrite, raise_on_error=fail_fast,
            )
        )
    return results


def _attempt_download(
    provider: Provider,
    ref: SoundRef,
    dest_dir: Path,
    manifest: Path,
    *,
    done: dict[tuple[str, str], str],
    taken: set[str],
    overwrite: bool,
    lock=None,
    raise_on_error: bool = False,
) -> DownloadResult:
    """Attempt one download and checkpoint its outcome to the manifest.

    Returns the DownloadResult. With ``raise_on_error=True`` (sequential
    --fail-fast), a failed attempt records its error to the manifest, then
    re-raises the DownloadError; otherwise the error result is returned and
    the loop continues. ``lock`` (a threading.Lock) guards the shared ``taken``
    set and manifest appends when the caller runs concurrently.
    """
    key = (ref.provider, ref.provider_id)
    if not overwrite and key in done and (dest_dir / done[key]).exists():
        log.info("skip %s/%s (already downloaded)", ref.provider, ref.provider_id)
        return DownloadResult(dest_dir / done[key], status="skipped")

    # Name collision handling: unique within this run + on disk.
    stem = _safe_stem(ref)
    ext = (ref.file_format or "bin").lstrip(".")
    if lock is not None:
        with lock:
            target = unique_path(dest_dir, stem, ext, taken=taken)
            taken.add(target.name)
    else:
        target = unique_path(dest_dir, stem, ext, taken=taken)
        taken.add(target.name)

    started_at = _now()
    t0 = time.monotonic()
    try:
        result = provider.download(ref, dest_dir, target=target)
        elapsed_s = round(time.monotonic() - t0, 3)
        result.started_at = started_at
        result.elapsed_s = elapsed_s
        record = ref_record(ref)
        record.update(
            {
                "status": "downloaded",
                "local_file": target.name,
                "downloaded_at": _now(),
                "started_at": started_at,
                "elapsed_s": elapsed_s,
                "bytes": result.bytes,
                "checksum": result.checksum or ref.checksum,
                "error": None,
            }
        )
        _append_record(manifest, record, lock)
        log.info("downloaded %s -> %s", ref.provider_id, target.name)
        return result
    except DownloadError as exc:
        elapsed_s = round(time.monotonic() - t0, 3)
        record = ref_record(ref)
        record.update(
            {
                "status": "error",
                "local_file": None,
                "started_at": started_at,
                "elapsed_s": elapsed_s,
                "error": str(exc),
            }
        )
        _append_record(manifest, record, lock)
        log.error("failed %s/%s: %s", ref.provider, ref.provider_id, exc)
        if raise_on_error:
            raise
        return DownloadResult(local_path=target, bytes=0, status="error", error=str(exc),
                              started_at=started_at, elapsed_s=elapsed_s)


def _append_record(manifest: Path, record: dict, lock=None) -> None:
    if lock is not None:
        with lock:
            append_record(manifest, record)
    else:
        append_record(manifest, record)


def _download_threaded(
    provider: Provider,
    refs: list[SoundRef],
    dest_dir: Path,
    manifest: Path,
    *,
    done: dict[tuple[str, str], str],
    overwrite: bool,
    fail_fast: bool,
    workers: int,
) -> list[DownloadResult]:
    """Parallel download with a bounded pool; results in ref order.

    ``taken`` and manifest appends are guarded by a single lock so filenames
    stay unique and checkpoints don't interleave. With --fail-fast the first
    error trips a stop flag, queued futures are cancelled, and after running
    futures drain the DownloadError is re-raised (record-then-raise, matching
    the sequential path).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading

    results: list[DownloadResult | None] = [None] * len(refs)
    io_lock = threading.Lock()
    taken: set[str] = set()
    stop = threading.Event()
    first_error: str | None = None

    def attempt(idx: int, ref: SoundRef) -> DownloadResult:
        return _attempt_download(
            provider, ref, dest_dir, manifest,
            done=done, taken=taken, overwrite=overwrite, lock=io_lock,
        )

    executor = ThreadPoolExecutor(max_workers=workers)
    futures = {executor.submit(attempt, idx, ref): idx for idx, ref in enumerate(refs)}
    try:
        for future in as_completed(futures):
            idx = futures[future]
            result = future.result()
            results[idx] = result
            if fail_fast and result.status == "error":
                if first_error is None:
                    first_error = result.error
                stop.set()
                executor.shutdown(wait=False, cancel_futures=True)
                break
    finally:
        executor.shutdown(wait=True)

    if first_error is not None:
        raise DownloadError(first_error)
    return results  # type: ignore[return-value]


def _resume_done(manifest: Path) -> dict[tuple[str, str], str]:
    """Last-wins pass over the manifest for resume: ``(provider, provider_id)
    -> local_file`` for every sound whose most recent record is a completed
    download.

    Streams the file and keeps only the tiny per-sound ``(status, local_file)``
    tuple instead of materializing every record as an object, so a huge
    manifest doesn't blow up memory just to resume.
    """
    pending: dict[tuple[str, str], tuple[str, str]] = {}
    if not manifest.exists():
        return {}
    try:
        fh = manifest.open()
    except OSError:
        return {}
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue  # tolerate a corrupt trailing line
            key = (rec.get("provider", ""), str(rec.get("provider_id", "")))
            pending[key] = (rec.get("status", ""), rec.get("local_file") or "")
    return {key: lf for key, (status, lf) in pending.items() if status == "downloaded" and lf}


def _safe_stem(ref: SoundRef) -> str:
    from .names import sanitize_stem

    return sanitize_stem(ref.name, f"sound-{ref.provider_id}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
