"""soundfetch — high-level, provider-agnostic API.

This module is the Python-library entry point.  Everything here is provider-
agnostic; provider-specific behavior arrives either through the provider
name (resolved via the lazy REGISTRY) or through explicitly constructed
Provider instances.  The CLI in ``cli.py`` is a thin wrapper over these
functions.

Examples
--------
    import soundfetch

    refs = soundfetch.search("piano", provider="freesound", license="cc0")
    soundfetch.save_search(refs, "out/manifest.jsonl")
    soundfetch.download(refs, dest_dir="out/")

Custom providers / explicit config:

    from soundfetch.providers.freesound.provider import FreesoundProvider

    api_key = FreesoundProvider(api_key="...")  # or let env vars resolve
    refs = soundfetch.search(
        "piano", provider="freesound",
        providers={"freesound": api_key},
    )
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable

from .core.engine import (
    download_refs,
    ref_record,
    search_all,
    write_search_records,
)
from .core.manifest import iter_latest, latest_by_sound, read_records
from .core.model import DownloadResult, SearchParams, SoundRef
from .core.provider import Provider, get_provider, provider_names

__all__ = [
    # Types (re-exported for library consumers)
    "SearchParams",
    "SoundRef",
    "DownloadResult",
    "Provider",
    "provider_names",
    # Functional API
    "search",
    "download",
    "save_search",
    "refs_from_manifest",
    # Manifest readers (dataset-index use case)
    "read_records",
    "iter_latest",
    "latest_by_sound",
    "ref_record",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _join(value: str | tuple[str, ...]) -> str:
    return ",".join(value) if isinstance(value, tuple) else value


def _resolve_provider(
    name: str,
    providers: dict[str, Provider] | None,
) -> Provider:
    return (providers or {}).get(name) or get_provider(name)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def search(
    query: str,
    *,
    provider: str = "freesound",
    providers: dict[str, Provider] | None = None,
    license: str | tuple[str, ...] | None = None,
    duration: str | None = None,
    tag: str | tuple[str, ...] | None = None,
    gen_ai: str | None = None,
    raw_filter: str | None = None,
    sort: str | None = None,
    page_size: int = 50,
    max_results: int | None = None,
    extra: dict[str, Any] | None = None,
    on_page: Callable[[Any, int], None] | None = None,
    pacing=None,
) -> list[SoundRef]:
    """Search a provider and return ``SoundRef`` results (no files written).

    ``provider`` names a registered provider; ``providers`` may inject
    already-constructed Provider instances (keyed by provider name) for
    explicit config (e.g. an API key passed directly rather than read
    from the environment).

    Filter kwargs translate to the provider-agnostic filters dict that
    every provider's ``filters.py`` consumes.  Keys that a provider
    doesn't support (e.g. ``duration`` for Internet Archive) are
    silently ignored, so the same call can fan out to multiple sources.
    """
    filters: dict[str, str] = {}
    if license is not None:
        filters["license"] = _join(license)
    if duration is not None:
        filters["duration"] = duration
    if tag is not None:
        filters["tag"] = _join(tag)
    if gen_ai is not None:
        filters["gen_ai"] = gen_ai
    if raw_filter is not None:
        filters["raw"] = raw_filter  # matches providers/*/filters.py key

    prov = _resolve_provider(provider, providers)
    params = SearchParams(
        query=query,
        filters=filters,
        page_size=page_size,
        max_results=max_results,
        sort=sort,
        extra=extra or {"page": 1},
    )
    return search_all(prov, params, on_page=on_page, pacing=pacing)


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------


def download(
    refs: Iterable[SoundRef],
    *,
    dest_dir: str | Path,
    manifest: str | Path | None = None,
    resume: bool = True,
    overwrite: bool = False,
    fail_fast: bool = False,
    rate_delay: float = 0.0,
    workers: int = 1,
    pacing=None,
    providers: dict[str, Provider] | None = None,
) -> list[DownloadResult]:
    """Download refs, checkpointing each attempt to ``manifest``.

    Refs are grouped by their ``.provider`` field; each group is
    dispatched to its registered provider (or an injected one via
    ``providers``).  Mixed-provider manifests therefore work correctly.

    ``manifest`` defaults to ``dest_dir/manifest.jsonl``. ``workers > 1``
    downloads each provider group in parallel (bounded pool); ``pacing`` (a
    core.pacing.Pacing) paces every request across search + download so a
    combined run stays under the provider's rate ceiling.
    """
    if not isinstance(refs, list):
        refs = list(refs)
    if not refs:
        return []
    dest = Path(dest_dir)
    man = Path(manifest) if manifest else dest / "manifest.jsonl"

    grouped: dict[str, list[SoundRef]] = {}
    for ref in refs:
        grouped.setdefault(ref.provider, []).append(ref)

    results: list[DownloadResult] = []
    for name, group in grouped.items():
        prov = _resolve_provider(name, providers)
        results.extend(
            download_refs(
                prov,
                group,
                dest,
                man,
                resume=resume,
                overwrite=overwrite,
                fail_fast=fail_fast,
                rate_delay=rate_delay,
                workers=workers,
                pacing=pacing,
            )
        )
    return results


# ---------------------------------------------------------------------------
# manifest / search-record helpers
# ---------------------------------------------------------------------------


def save_search(refs: Iterable[SoundRef], manifest: str | Path) -> None:
    """Write search results to a manifest as ``status:"listed"`` records."""
    write_search_records(Path(manifest), list(refs))


def refs_from_manifest(
    manifest: str | Path,
    *,
    skip_downloaded: bool = True,
) -> list[SoundRef]:
    """Reconstruct ``SoundRef`` entries from a manifest.

    Only the latest record per ``(provider, provider_id)`` is considered
    (last-wins dedup).  By default sounds already marked ``status:
    "downloaded"`` with a local file are skipped — feed the result into
    ``download()`` for checkpoint-resume behavior.  Pass
    ``skip_downloaded=False`` to include them so ``download()``'s own
    resume check can report them as ``skipped``.
    """
    refs: list[SoundRef] = []
    for record in iter_latest(Path(manifest)):
        if skip_downloaded and record.get("status") == "downloaded" and record.get("local_file"):
            continue
        refs.append(
            SoundRef(
                provider=record.get("provider", ""),
                provider_id=str(record.get("provider_id", "")),
                name=record.get("name", ""),
                url=record.get("url", ""),
                download_url=record.get("download_url"),
                file_format=record.get("file_format"),
                checksum=record.get("checksum"),
                metadata=record.get("metadata") or {},
            )
        )
    return refs
