"""Openverse provider for the stable public audio search API.

Openverse aggregates metadata for files hosted by third parties. Search maps
that normalized metadata into ``SoundRef`` while download deliberately goes
through the shared downloader to the result's upstream media URL.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from ...core.downloader import DownloadError, stream_to_file
from ...core.model import DownloadResult, SearchPage, SearchParams, SoundRef
from ...core.names import sanitize_ext
from ...core.net import get_json
from ...core.pacing import default_pacing
from ...core.provider import ProgressCallback
from .filters import build_params

SEARCH_URL = "https://api.openverse.org/v1/audio/"
ANONYMOUS_PAGE_SIZE = 20

_METADATA_FIELDS = (
    "source",
    "provider",
    "foreign_landing_url",
    "creator",
    "creator_url",
    "license",
    "license_version",
    "license_url",
    "attribution",
    "category",
    "duration",
    "filesize",
    "filetype",
    "bit_rate",
    "sample_rate",
    "tags",
    "genres",
    "indexed_on",
    "mature",
    "detail_url",
)


class OpenverseProvider:
    name = "openverse"

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.rate_limiter = None

    def search(
        self,
        params: SearchParams,
        *,
        progress: ProgressCallback | None = None,
    ) -> SearchPage:
        page_number = int(params.extra.get("page", 1))
        query_params: dict[str, Any] = {
            "q": params.query,
            "page": page_number,
            "page_size": min(max(1, params.page_size), ANONYMOUS_PAGE_SIZE),
            "filter_dead": "true",
            "mature": "false",
        }
        query_params.update(build_params(params.filters))
        payload = get_json(
            self.session,
            SEARCH_URL,
            params=query_params,
            limiter=self.rate_limiter or default_pacing().limiter(self.name),
        )

        raw_results = payload.get("results")
        if not isinstance(raw_results, list):
            raise ValueError("Openverse response is missing a results list")
        results = [ref for item in raw_results if (ref := self._to_ref(item)) is not None]
        current_page = _integer(payload.get("page"), page_number)
        page_count = _integer(payload.get("page_count"), current_page)
        total = _integer(payload.get("result_count"), len(results))
        return SearchPage(results=results, total=total, has_more=current_page < page_count)

    def _to_ref(self, item: Any) -> SoundRef | None:
        if not isinstance(item, dict):
            return None
        identifier = item.get("id")
        download_url = item.get("url")
        landing_url = item.get("foreign_landing_url")
        if not identifier or not download_url or not landing_url:
            return None

        metadata = {key: item[key] for key in _METADATA_FIELDS if key in item}
        metadata["openverse_id"] = str(identifier)
        if "duration" in metadata:
            metadata["duration_ms"] = metadata.pop("duration")

        file_format = _file_format(item.get("filetype"))
        return SoundRef(
            provider=self.name,
            provider_id=str(identifier),
            name=str(item.get("title") or f"openverse-{identifier}"),
            url=str(landing_url),
            download_url=str(download_url),
            file_format=file_format,
            metadata=metadata,
        )

    def download(
        self,
        ref: SoundRef,
        dest_dir: Path,
        *,
        target: Path | None = None,
    ) -> DownloadResult:
        dest_dir.mkdir(parents=True, exist_ok=True)
        if not ref.download_url:
            raise DownloadError(f"no download URL for Openverse item {ref.provider_id}")
        ext = sanitize_ext(ref.file_format, "bin")
        final_path = target or (dest_dir / f"{ref.provider_id}.{ext}")
        written = stream_to_file(
            ref.download_url,
            final_path,
            session=self.session,
            limiter=self.rate_limiter,
        )
        return DownloadResult(local_path=final_path, bytes=written, status="downloaded")

    def status(self) -> dict[str, bool]:
        return {"auth_required": False}


def _integer(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _file_format(value: Any) -> str:
    """Normalize known catalog format labels into real file extensions."""
    normalized = sanitize_ext(str(value) if value is not None else None, "bin").lower()
    return {"mp32": "mp3", "mpeg": "mp3"}.get(normalized, normalized)
