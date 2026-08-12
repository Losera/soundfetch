"""Video provider (yt-dlp-based) — URL- or query-driven, audio-only.

Unlike Freesound/Archive, a "query" here can be a literal URL (a single
video, playlist, or channel) or free text, which is treated as a YouTube
search via yt-dlp's `ytsearchN:` pseudo-URL. yt-dlp has no offset-based
pagination for search results, so search() lists up to `max_results` (or
50, by default) candidates once via a cheap flat extraction, caches them,
and pages through that cached list in memory — only fully resolving the
current page's items (one `extract_info` call each) to pick a concrete
audio-only stream, the same one-extra-request-per-item pattern the
Internet Archive provider uses for the same reason (core.engine needs
SoundRef.file_format before download() is ever called).

yt-dlp's resolved stream URLs are signed by the CDN and expire (observed:
a few hours for YouTube). Caching one in the manifest and downloading from
it later — which is exactly what soundfetch's --manifest workflow does —
would 401 once it expires. So download() ignores SoundRef.download_url
and re-resolves a fresh stream URL from SoundRef.url (the permanent
watch-page URL) on every call.

Needs the `yt-dlp` package (`pip install "soundfetch[video]"`) — imported
lazily inside `_ydl()` so this module (and `soundfetch sources`/`--help`)
works without it installed; only actually using the provider requires it.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from ...core.downloader import DownloadError, stream_to_file
from ...core.model import DownloadResult, SearchPage, SearchParams, SoundRef
from ...core.names import sanitize_ext

log = logging.getLogger(__name__)

DEFAULT_SEARCH_CAP = 50  # ytsearchN: has no offset/pagination; fetched once and paged in-memory.


def _ydl(**opts: Any):
    try:
        import yt_dlp
    except ImportError as exc:
        raise RuntimeError(
            'the video provider needs yt-dlp: run `pip install "soundfetch[video]"`'
        ) from exc
    base = {"quiet": True, "no_warnings": True, "skip_download": True}
    base.update(opts)
    return yt_dlp.YoutubeDL(base)


class VideoProvider:
    name = "video"

    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        # RateLimiter attached by core.engine once pacing is configured.
        self.rate_limiter = None
        self._entries_cache: dict[str, list[dict]] = {}

    # -- Search -----------------------------------------------------------------

    def search(self, params: SearchParams, *, progress=None) -> SearchPage:
        page = int(params.extra.get("page", 1))
        entries = self._list_entries(params.query, params.max_results or DEFAULT_SEARCH_CAP)

        start = (page - 1) * params.page_size
        end = start + params.page_size
        page_entries = entries[start:end]

        results: list[SoundRef] = []
        for entry in page_entries:
            url = entry.get("url") or entry.get("webpage_url") or str(entry.get("id"))
            try:
                full = self._resolve(url)
            except Exception as exc:
                log.info("skip %s: %s", entry.get("id"), exc)
                continue
            ref = self._to_ref(full, filters=params.filters)
            if ref is not None:
                results.append(ref)

        has_more = end < len(entries)
        return SearchPage(results=results, total=len(entries), has_more=has_more)

    def _list_entries(self, query: str, limit: int) -> list[dict]:
        if query in self._entries_cache:
            return self._entries_cache[query]
        if _is_url(query) and not _is_safe_remote_url(query):
            raise ValueError(f"refusing to fetch a private/internal URL: {query!r}")
        target = query if _is_url(query) else f"ytsearch{limit}:{query}"
        with _ydl(extract_flat=True) as ydl:
            info = ydl.extract_info(target, download=False)

        entries = info.get("entries")
        if entries is None:
            # A single video, not a playlist/search — synthesize one entry
            # anchored on `target` (the URL we were given), since the flat
            # info's own "url"/"webpage_url" fields are often null here.
            entries = [{"id": info.get("id"), "url": target, "title": info.get("title")}]
        entries = [e for e in entries if e]  # flat extraction can yield None for dropped items

        self._entries_cache[query] = entries
        return entries

    def _resolve(self, url: str) -> dict:
        with _ydl() as ydl:
            return ydl.extract_info(url, download=False)

    def _to_ref(self, info: dict, *, filters: dict[str, str]) -> SoundRef | None:
        audio_format = _pick_audio_format(info.get("formats") or [])
        if audio_format is None:
            log.info("skip %s: no audio-only stream", info.get("id"))
            return None

        license_code = filters.get("license")
        if license_code and license_code != "any" and not _matches_license(info.get("license"), license_code):
            return None

        metadata = {
            k: info.get(k)
            for k in (
                "id",
                "title",
                "uploader",
                "uploader_url",
                "duration",
                "license",
                "upload_date",
                "webpage_url",
                "extractor",
            )
        }
        metadata["format_id"] = audio_format.get("format_id")

        return SoundRef(
            provider=self.name,
            provider_id=str(info.get("id")),
            name=info.get("title") or str(info.get("id")),
            url=info.get("webpage_url") or "",
            download_url=audio_format.get("url"),
            file_format=audio_format.get("ext") or "m4a",
            checksum=None,  # yt-dlp streams don't expose one
            metadata=metadata,
        )

    # -- Download ---------------------------------------------------------------

    def download(
        self, ref: SoundRef, dest_dir: Path, *, target: Path | None = None
    ) -> DownloadResult:
        dest_dir.mkdir(parents=True, exist_ok=True)
        if not ref.url:
            raise DownloadError(f"no watch URL for video {ref.provider_id}")

        try:
            full = self._resolve(ref.url)
        except Exception as exc:
            raise DownloadError(f"could not resolve {ref.provider_id}: {exc}") from exc

        audio_format = _pick_audio_format(full.get("formats") or [])
        if audio_format is None:
            raise DownloadError(f"no audio-only stream for video {ref.provider_id}")

        ext = sanitize_ext(audio_format.get("ext") or ref.file_format, "m4a")
        final_path = target or (dest_dir / f"{ref.provider_id}.{ext}")
        written = stream_to_file(
            audio_format["url"],
            final_path,
            session=self.session,
            headers=audio_format.get("http_headers"),
            limiter=self.rate_limiter,
        )
        return DownloadResult(local_path=final_path, bytes=written, status="downloaded")

    # -- Health -----------------------------------------------------------------

    def status(self) -> dict[str, bool]:
        try:
            import yt_dlp  # noqa: F401

            installed = True
        except ImportError:
            installed = False
        return {"yt_dlp_installed": installed}


def _is_url(query: str) -> bool:
    return query.startswith("http://") or query.startswith("https://")


def _is_safe_remote_url(url: str) -> bool:
    """Reject URLs that resolve to a private, loopback, link-local, or
    otherwise non-public address.

    A URL-shaped `search_sounds` query is passed straight to yt-dlp's
    extractor, which fetches it — and `query` is model-supplied over MCP,
    so a prompt-injected instruction can plausibly reach this. Without this
    check it's a direct SSRF primitive against the host running the server
    (cloud metadata endpoints, internal services, ...).

    This is DNS-resolution-time filtering, not a complete SSRF defense: it
    does not protect against DNS rebinding between this check and yt-dlp's
    own fetch.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def _pick_audio_format(formats: list[dict]) -> dict | None:
    audio_only = [
        f for f in formats if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")
    ]
    if not audio_only:
        return None
    return max(audio_only, key=lambda f: f.get("abr") or f.get("tbr") or 0)


def _matches_license(license_str: str | None, code: str) -> bool:
    """Best-effort only: YouTube exposes license as a free-text string, not
    an enum, so only the one meaningful distinction (Creative Commons vs.
    everything else) is checked. Any other code is treated as unfiltered."""
    if code != "cc-by":
        return True
    return bool(license_str) and "creative commons" in license_str.lower()
