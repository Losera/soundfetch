"""Test doubles implementing the core.provider.Provider protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from soundfetch.core.downloader import DownloadError
from soundfetch.core.model import DownloadResult, SearchPage, SoundRef


class FakeProvider:
    """A scripted Provider: fixed search pages + a pluggable download outcome."""

    name = "fake"

    def __init__(
        self,
        pages: list[SearchPage] | None = None,
        download_fn: Callable[[SoundRef, Path, Path | None], DownloadResult] | None = None,
    ):
        self.pages = pages or []
        self.download_fn = download_fn
        self.search_calls: list[int] = []
        self.download_calls: list[str] = []

    def search(self, params, *, progress=None) -> SearchPage:
        page = int(params.extra["page"])
        self.search_calls.append(page)
        idx = page - 1
        if idx < len(self.pages):
            return self.pages[idx]
        return SearchPage(results=[], total=0, has_more=False)

    def download(self, ref: SoundRef, dest_dir: Path, *, target: Path | None = None) -> DownloadResult:
        self.download_calls.append(ref.provider_id)
        if self.download_fn:
            return self.download_fn(ref, dest_dir, target)
        final = target or (dest_dir / f"{ref.provider_id}.bin")
        final.write_bytes(b"data")
        return DownloadResult(local_path=final, bytes=4, status="downloaded")


def make_ref(provider_id: str, name: str = "sound", **kwargs) -> SoundRef:
    kwargs.setdefault("url", f"https://example.test/{provider_id}")
    kwargs.setdefault("file_format", "wav")
    return SoundRef(provider="fake", provider_id=provider_id, name=name, **kwargs)


def failing_download(exc: Exception | None = None):
    """A download_fn that always raises DownloadError."""

    def _fn(ref: SoundRef, dest_dir: Path, target: Path | None) -> DownloadResult:
        raise exc or DownloadError(f"boom on {ref.provider_id}")

    return _fn
