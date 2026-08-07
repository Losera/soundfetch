"""Internet Archive provider — advancedsearch.php + /download/<id>/<file>.

No auth: IA serves original-quality files to anyone. The one architectural
wrinkle versus Freesound is that an IA search result ("item") is a bundle
of files, not a single sound — a query hit doesn't say which file to
download. core.engine needs SoundRef.file_format before it ever calls
download() (for extension/naming), so this provider resolves one
representative audio file per item during search() itself, via a metadata
lookup per hit. That's an extra request per result versus Freesound, but
it's what keeps the core engine provider-agnostic: by the time a SoundRef
leaves search(), it points at one concrete file, same as any other source.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import requests

from ...core.downloader import DownloadError, stream_to_file
from ...core.model import DownloadResult, SearchPage, SearchParams, SoundRef
from ...core.net import get_json
from .filters import build_query

log = logging.getLogger(__name__)

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL = "https://archive.org/metadata/{identifier}"
DOWNLOAD_URL = "https://archive.org/download/{identifier}/{filename}"

SEARCH_FIELDS = ("identifier", "title", "description", "licenseurl", "downloads", "item_size")

# Audio file extensions we'll consider, best format first when a file is
# available in more than one (an item's "original" upload is usually a
# lossless wav/flac; mp3/ogg are IA-generated derivatives).
AUDIO_EXTENSIONS = ("flac", "wav", "aiff", "aif", "ogg", "mp3", "m4a")


class ArchiveProvider:
    name = "archive"

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()

    # -- Search -----------------------------------------------------------------

    def search(self, params: SearchParams, *, progress=None) -> SearchPage:
        page = int(params.extra.get("page", 1))
        query_params: dict[str, Any] = {
            "q": build_query(params.query, params.filters),
            "fl[]": list(SEARCH_FIELDS),
            "rows": params.page_size,
            "page": page,
            "output": "json",
        }
        if params.sort:
            query_params["sort[]"] = params.sort

        payload = get_json(self.session, SEARCH_URL, params=query_params)
        response = payload.get("response", {})
        docs = response.get("docs", [])
        num_found = int(response.get("numFound", 0))
        start = int(response.get("start", 0))

        results = [ref for ref in (self._to_ref(doc) for doc in docs) if ref is not None]
        has_more = (start + len(docs)) < num_found
        return SearchPage(results=results, total=num_found, has_more=has_more)

    def _to_ref(self, doc: dict) -> SoundRef | None:
        identifier = doc.get("identifier")
        if not identifier:
            return None
        picked = self._pick_audio_file(identifier)
        if picked is None:
            log.info("skip %s: no audio file in item", identifier)
            return None
        filename, file_format, checksum = picked
        return SoundRef(
            provider=self.name,
            provider_id=identifier,
            name=doc.get("title") or identifier,
            url=f"https://archive.org/details/{identifier}",
            download_url=DOWNLOAD_URL.format(identifier=identifier, filename=filename),
            file_format=file_format,
            checksum=checksum,
            metadata={**doc, "filename": filename},
        )

    def _pick_audio_file(self, identifier: str) -> tuple[str, str, str | None] | None:
        """Resolve one audio file for an item: prefer the original upload,
        then the best-quality extension among what's available."""
        payload = get_json(self.session, METADATA_URL.format(identifier=identifier))
        candidates = []
        for f in payload.get("files", []):
            name = f.get("name", "")
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if ext not in AUDIO_EXTENSIONS:
                continue
            is_derivative = f.get("source") != "original"
            candidates.append((is_derivative, AUDIO_EXTENSIONS.index(ext), name, ext, f.get("md5")))
        if not candidates:
            return None
        candidates.sort(key=lambda c: (c[0], c[1]))
        _, _, name, ext, md5 = candidates[0]
        return name, ext, md5

    # -- Download ---------------------------------------------------------------

    def download(
        self, ref: SoundRef, dest_dir: Path, *, target: Path | None = None
    ) -> DownloadResult:
        dest_dir.mkdir(parents=True, exist_ok=True)
        if not ref.download_url:
            raise DownloadError(f"no download URL for item {ref.provider_id}")

        ext = ref.file_format or "bin"
        final_path = target or (dest_dir / f"{ref.provider_id}.{ext}")
        written = stream_to_file(
            ref.download_url, final_path, session=self.session, checksum=ref.checksum
        )
        return DownloadResult(
            local_path=final_path, bytes=written, checksum=ref.checksum, status="downloaded"
        )

    # -- Health -----------------------------------------------------------------

    def status(self) -> dict[str, bool]:
        """No auth or config needed for this provider."""
        return {"auth_required": False}
