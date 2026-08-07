"""Freesound.org provider — search + pagination + preview/original downloads.

Direct API v2 calls (no freesound-python SDK): the SDK's Pager is what the
original script's one-page bug came from, and its download methods can't do
.part resume or expose Retry-After. Endpoint + filter + auth all live here.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import requests

from ...core.downloader import DownloadError, stream_to_file
from ...core.model import DownloadResult, SearchPage, SearchParams, SoundRef
from ...core.net import get_json
from .auth import AuthError, OAuthClient, TokenStore
from .filters import build_filter

log = logging.getLogger(__name__)

BASE_URL = "https://freesound.org/apiv2"
DEFAULT_FIELDS = (
    "id,name,url,description,tags,username,license,gen_ai_preference,duration,"
    "samplerate,channels,type,filesize,md5,created,score,previews,images"
)
PREVIEW_KEYS = {
    ("hq", "mp3"): "preview-hq-mp3",
    ("lq", "mp3"): "preview-lq-mp3",
    ("hq", "ogg"): "preview-hq-ogg",
    ("lq", "ogg"): "preview-lq-ogg",
}


class FreesoundProvider:
    name = "freesound"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        mode: str = "preview",
        preview_quality: str = "hq",
        preview_format: str = "mp3",
        session: requests.Session | None = None,
        config_dir: Path | None = None,
    ):
        self.api_key = api_key or os.environ.get("FREESOUND_API_KEY")
        self.mode = mode
        self.preview_quality = preview_quality
        self.preview_format = preview_format
        self.session = session or requests.Session()
        self._token = None
        self._token_error: AuthError | None = None
        self._oauth: OAuthClient | None = None
        self._config_dir = config_dir
        if mode not in ("preview", "original"):
            raise ValueError(f"invalid mode {mode!r}; expected 'preview' or 'original'")
        if preview_format not in ("mp3", "ogg"):
            raise ValueError(f"invalid preview format {preview_format!r}; expected mp3|ogg")

    # -- OAuth2 lazy init (only touched for original downloads) -----------------

    def _oauth_client(self) -> OAuthClient:
        if self._oauth is None:
            client_id = os.environ.get("FREESOUND_CLIENT_ID")
            client_secret = os.environ.get("FREESOUND_CLIENT_SECRET")
            if not client_id or not client_secret:
                raise AuthError(
                    "original downloads need FREESOUND_CLIENT_ID and "
                    "FREESOUND_CLIENT_SECRET set. Run `soundfetch freesound auth`."
                )
            from .auth import DEFAULT_CONFIG_DIR

            store = TokenStore(
                (self._config_dir or Path(os.environ.get("SOUNDFETCH_CONFIG_DIR", DEFAULT_CONFIG_DIR)))
                / "freesound.json"
            )
            self._oauth = OAuthClient(client_id, client_secret, store=store, session=self.session)
        return self._oauth

    def _bearer_token(self) -> str:
        if self._token is None:
            self._token = self._oauth_client().get_token().access_token
        return self._token

    # -- Search -----------------------------------------------------------------

    def search(self, params: SearchParams, *, progress=None) -> SearchPage:
        if not self.api_key:
            raise RuntimeError(
                "FREESOUND_API_KEY is not set. Add it to .env or the environment "
                "(get a key at https://freesound.org/apiv2/apply/)."
            )
        filter_str = build_filter(params.filters)
        page = int(params.extra.get("page", 1))
        page_size = min(params.page_size, 150)

        query_params: dict[str, Any] = {
            "query": params.query,
            "fields": DEFAULT_FIELDS,
            "page": page,
            "page_size": page_size,
            "token": self.api_key,
        }
        if filter_str:
            query_params["filter"] = filter_str
        if params.sort:
            query_params["sort"] = params.sort
        descriptors = params.extra.get("with_descriptors")
        if descriptors:
            query_params["fields"] = DEFAULT_FIELDS + "," + ",".join(descriptors)

        payload = get_json(self.session, f"{BASE_URL}/search/", params=query_params)

        results = [
            self._to_ref(item)
            for item in payload.get("results", [])
        ]
        has_more = bool(payload.get("next"))
        return SearchPage(results=results, total=payload.get("count", 0), has_more=has_more)

    def _to_ref(self, item: dict) -> SoundRef:
        metadata = dict(item)
        previews = metadata.get("previews") or {}
        preview_url = previews.get(
            PREVIEW_KEYS.get((self.preview_quality, self.preview_format), "preview-hq-mp3")
        )
        return SoundRef(
            provider=self.name,
            provider_id=str(item.get("id")),
            name=item.get("name", ""),
            url=item.get("url", ""),
            download_url=preview_url,
            file_format=metadata.get("type") or self.preview_format,
            checksum=metadata.get("md5"),
            metadata=metadata,
        )

    # -- Download ---------------------------------------------------------------

    def download(
        self, ref: SoundRef, dest_dir: Path, *, target: Path | None = None
    ) -> DownloadResult:
        dest_dir.mkdir(parents=True, exist_ok=True)

        if self.mode == "preview":
            return self._download_preview(ref, dest_dir, target)
        return self._download_original(ref, dest_dir, target)

    def _download_preview(
        self, ref: SoundRef, dest_dir: Path, target: Path | None
    ) -> DownloadResult:
        previews = ref.metadata.get("previews") or {}
        key = PREVIEW_KEYS.get((self.preview_quality, self.preview_format), "preview-hq-mp3")
        url = previews.get(key) or ref.download_url
        if not url:
            raise DownloadError(f"no preview URL for sound {ref.provider_id}")

        ext = self.preview_format
        final_path = target or (dest_dir / f"{ref.provider_id}.{ext}")
        written = stream_to_file(url, final_path, session=self.session, checksum=None)
        return DownloadResult(local_path=final_path, bytes=written, status="downloaded")

    def _download_original(
        self, ref: SoundRef, dest_dir: Path, target: Path | None
    ) -> DownloadResult:
        token = self._bearer_token()
        sound_id = ref.provider_id
        url = f"{BASE_URL}/sounds/{sound_id}/download/"
        headers = {"Authorization": f"Bearer {token}"}

        ext = (ref.file_format or "wav").lstrip(".")
        final_path = target or (dest_dir / f"{ref.provider_id}.{ext}")
        written = stream_to_file(
            url, final_path, session=self.session, headers=headers, checksum=ref.checksum
        )
        return DownloadResult(
            local_path=final_path, bytes=written, checksum=ref.checksum, status="downloaded"
        )

    # -- Health -----------------------------------------------------------------

    def status(self) -> dict[str, bool]:
        """What's configured for this provider (for `soundfetch freesound status`)."""
        has_oauth_creds = bool(
            os.environ.get("FREESOUND_CLIENT_ID") and os.environ.get("FREESOUND_CLIENT_SECRET")
        )
        token_present = False
        if has_oauth_creds:
            token_present = self._oauth_client().store.load() is not None
        return {
            "api_key": bool(self.api_key),
            "client_id": has_oauth_creds,
            "client_secret": has_oauth_creds,
            "oauth_token": token_present,
        }
