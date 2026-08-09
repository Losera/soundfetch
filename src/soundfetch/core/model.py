"""Provider-agnostic data model for soundfetch.

These dataclasses are the contract between providers and the core engine.
A new provider maps its API responses onto SoundRef / SearchPage; the core
engine never sees provider-specific payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SearchParams:
    """A provider-agnostic search request."""

    query: str
    # Provider-agnostic filters, e.g. {"license": "cc0", "duration": "[1 TO 30]"}
    filters: dict[str, str] = field(default_factory=dict)
    page_size: int = 50
    # None = page until the provider reports no more results.
    max_results: int | None = None
    sort: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SoundRef:
    """A reference to one downloadable sound, serializable to the manifest."""

    provider: str
    provider_id: str
    name: str
    # The canonical public URL for the sound (for attribution / dedup).
    url: str = ""
    # Direct download URL when known (always for previews; originals after auth).
    download_url: str | None = None
    file_format: str | None = None  # "mp3" | "ogg" | "wav" | "flac" ...
    checksum: str | None = None
    # Full provider metadata — serialized verbatim into the manifest record.
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchPage:
    """One page of search results."""

    results: list[SoundRef]
    total: int
    has_more: bool


@dataclass
class DownloadResult:
    """Outcome of downloading one sound."""

    local_path: Path
    bytes: int = 0
    checksum: str | None = None
    status: str = "downloaded"  # "downloaded" | "skipped" | "error"
    error: str | None = None
    started_at: str | None = None  # ISO-8601 UTC epoch
    elapsed_s: float | None = None  # wall-clock seconds for the download
