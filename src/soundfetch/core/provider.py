"""Provider protocol + lazy registry.

A provider is anything with two methods:

    search(params: SearchParams) -> SearchPage
    download(ref: SoundRef, dest_dir: Path) -> DownloadResult

The core engine owns pagination, checkpointing, naming and resume, so
providers never duplicate that logic. Adding a source = one module that
implements the Protocol plus one line in REGISTRY.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Protocol

from .model import DownloadResult, SearchPage, SearchParams, SoundRef

# Provider name -> "module:ClassName". Resolved lazily so importing core
# never pulls provider dependencies (requests, yt-dlp, ...).
REGISTRY: dict[str, str] = {
    "freesound": "soundfetch.providers.freesound.provider:FreesoundProvider",
    "archive": "soundfetch.providers.archive.provider:ArchiveProvider",
    "video": "soundfetch.providers.video.provider:VideoProvider",
}


class Provider(Protocol):
    name: str

    def search(
        self, params: SearchParams, *, progress=None
    ) -> SearchPage: ...

    def download(
        self, ref: SoundRef, dest_dir: Path, *, target: Path | None = None
    ) -> DownloadResult: ...


def get_provider(name: str) -> Provider:
    """Resolve a provider name to an instance via the lazy registry."""
    try:
        import_path = REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"unknown provider {name!r}; known: {', '.join(sorted(REGISTRY))}"
        ) from None

    module_name, _, class_name = import_path.partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, class_name)()


def provider_names() -> list[str]:
    """Registered provider names (sorted, stable)."""
    return sorted(REGISTRY)
