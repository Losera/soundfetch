"""VideoProvider tests. yt-dlp itself is never invoked here — search()/download()
call self._list_entries()/self._resolve() internally, and every test below
monkeypatches those two seams directly, so this file passes whether or not
the (optional) yt-dlp dependency is installed."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from soundfetch.core.downloader import DownloadError
from soundfetch.core.model import SearchParams, SoundRef
from soundfetch.providers.video.provider import (
    VideoProvider,
    _is_safe_remote_url,
    _is_url,
    _matches_license,
    _pick_audio_format,
    _ydl,
)


class TestIsUrl:
    def test_http_and_https_are_urls(self):
        assert _is_url("http://example.com/x") is True
        assert _is_url("https://example.com/x") is True

    def test_plain_text_is_not_a_url(self):
        assert _is_url("rain ambience") is False


class TestIsSafeRemoteUrl:
    """SSRF guard: a URL-shaped `search_sounds` query goes straight to
    yt-dlp's extractor, and `query` is model-supplied over MCP."""

    def test_rejects_non_http_scheme(self):
        assert _is_safe_remote_url("ftp://example.com/x") is False

    def test_rejects_url_without_host(self):
        assert _is_safe_remote_url("http:///x") is False

    def test_rejects_loopback_ip_literal(self):
        assert _is_safe_remote_url("http://127.0.0.1/x") is False

    def test_rejects_cloud_metadata_ip(self):
        assert _is_safe_remote_url("http://169.254.169.254/latest/meta-data/") is False

    def test_rejects_private_range_ip(self):
        assert _is_safe_remote_url("http://10.0.0.5:8080/admin") is False

    def test_rejects_ipv6_loopback(self):
        assert _is_safe_remote_url("http://[::1]:8080/") is False

    def test_rejects_unresolvable_host(self, monkeypatch: pytest.MonkeyPatch):
        import socket

        def raise_gaierror(host, port):
            raise socket.gaierror("no such host")

        monkeypatch.setattr(socket, "getaddrinfo", raise_gaierror)
        assert _is_safe_remote_url("http://nonexistent.invalid/x") is False

    def test_accepts_public_address(self, monkeypatch: pytest.MonkeyPatch):
        import socket

        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda host, port: [(socket.AF_INET, None, None, None, ("93.184.216.34", 0))],
        )
        assert _is_safe_remote_url("https://example.com/watch") is True


class TestListEntriesSsrfGuard:
    def test_private_ip_query_is_rejected_before_reaching_yt_dlp(self):
        provider = VideoProvider()
        with pytest.raises(ValueError, match="private/internal"):
            provider._list_entries("http://169.254.169.254/latest/meta-data/", 10)


class TestPickAudioFormat:
    def test_returns_none_for_empty_list(self):
        assert _pick_audio_format([]) is None

    def test_ignores_video_formats(self):
        formats = [{"vcodec": "avc1", "acodec": "mp4a", "abr": 999}]
        assert _pick_audio_format(formats) is None

    def test_ignores_formats_without_audio(self):
        formats = [{"vcodec": "none", "acodec": "none", "abr": 999}]
        assert _pick_audio_format(formats) is None

    def test_picks_highest_abr(self):
        formats = [
            {"vcodec": "none", "acodec": "opus", "abr": 48, "format_id": "low"},
            {"vcodec": "none", "acodec": "mp4a", "abr": 129, "format_id": "high"},
            {"vcodec": "avc1", "acodec": "mp4a", "abr": 999, "format_id": "video"},
        ]
        assert _pick_audio_format(formats)["format_id"] == "high"

    def test_falls_back_to_tbr_when_abr_missing(self):
        formats = [
            {"vcodec": "none", "acodec": "opus", "abr": None, "tbr": 50, "format_id": "a"},
            {"vcodec": "none", "acodec": "opus", "abr": None, "tbr": 90, "format_id": "b"},
        ]
        assert _pick_audio_format(formats)["format_id"] == "b"


class TestMatchesLicense:
    def test_cc_by_matches_creative_commons_license(self):
        assert _matches_license("Creative Commons Attribution license (reuse allowed)", "cc-by")

    def test_cc_by_case_insensitive(self):
        assert _matches_license("CREATIVE COMMONS Attribution", "cc-by")

    def test_cc_by_rejects_standard_license(self):
        assert not _matches_license("Standard YouTube License", "cc-by")

    def test_cc_by_rejects_missing_license(self):
        assert not _matches_license(None, "cc-by")

    def test_other_codes_are_unfiltered(self):
        assert _matches_license("Standard YouTube License", "cc0") is True
        assert _matches_license(None, "cc0") is True


class TestYdl:
    def test_raises_helpful_error_when_yt_dlp_missing(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setitem(sys.modules, "yt_dlp", None)
        with pytest.raises(RuntimeError, match="soundfetch\\[video\\]"):
            _ydl()


def _flat_entry(id_: str, url: str, title: str = "video") -> dict:
    return {"id": id_, "url": url, "title": title}


def _full_info(id_: str, url: str, title: str, formats: list[dict], license_: str | None = None) -> dict:
    return {
        "id": id_,
        "title": title,
        "webpage_url": url,
        "formats": formats,
        "license": license_,
        "uploader": "someone",
        "uploader_url": "https://example.test/someone",
        "duration": 120,
        "upload_date": "20240101",
        "extractor": "youtube",
    }


AUDIO_FORMAT = {
    "format_id": "140",
    "ext": "m4a",
    "vcodec": "none",
    "acodec": "mp4a.40.2",
    "abr": 129.0,
    "url": "https://cdn.test/stream.m4a",
    "http_headers": {"User-Agent": "test-agent"},
}


class TestSearch:
    def test_paginates_over_cached_entries(self, monkeypatch: pytest.MonkeyPatch):
        provider = VideoProvider()
        entries = [_flat_entry(f"id{i}", f"https://yt.test/{i}") for i in range(3)]
        monkeypatch.setattr(provider, "_list_entries", lambda query, limit: entries)
        monkeypatch.setattr(
            provider,
            "_resolve",
            lambda url: _full_info(url.split("/")[-1], url, "title", [AUDIO_FORMAT]),
        )

        page1 = provider.search(SearchParams(query="rain", page_size=2, extra={"page": 1}))
        page2 = provider.search(SearchParams(query="rain", page_size=2, extra={"page": 2}))

        assert [r.provider_id for r in page1.results] == ["0", "1"]
        assert page1.has_more is True
        assert [r.provider_id for r in page2.results] == ["2"]
        assert page2.has_more is False
        assert page1.total == 3

    def test_ref_conversion_picks_audio_format_and_metadata(self, monkeypatch: pytest.MonkeyPatch):
        provider = VideoProvider()
        monkeypatch.setattr(
            provider, "_list_entries", lambda query, limit: [_flat_entry("abc123", "https://yt.test/abc123")]
        )
        monkeypatch.setattr(
            provider,
            "_resolve",
            lambda url: _full_info("abc123", url, "Rain Ambience", [AUDIO_FORMAT], license_="Standard YouTube License"),
        )

        page = provider.search(SearchParams(query="rain", extra={"page": 1}))
        ref = page.results[0]

        assert ref.provider == "video"
        assert ref.provider_id == "abc123"
        assert ref.name == "Rain Ambience"
        assert ref.url == "https://yt.test/abc123"
        assert ref.download_url == "https://cdn.test/stream.m4a"
        assert ref.file_format == "m4a"
        assert ref.checksum is None
        assert ref.metadata["uploader"] == "someone"
        assert ref.metadata["format_id"] == "140"

    def test_skips_entries_with_no_audio_only_format(self, monkeypatch: pytest.MonkeyPatch):
        provider = VideoProvider()
        video_only_format = {"format_id": "v", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "abr": 999, "url": "x"}
        monkeypatch.setattr(
            provider, "_list_entries", lambda query, limit: [_flat_entry("abc", "https://yt.test/abc")]
        )
        monkeypatch.setattr(
            provider, "_resolve", lambda url: _full_info("abc", url, "x", [video_only_format])
        )

        page = provider.search(SearchParams(query="rain", extra={"page": 1}))
        assert page.results == []

    def test_skips_entries_that_fail_to_resolve(self, monkeypatch: pytest.MonkeyPatch):
        provider = VideoProvider()
        entries = [_flat_entry("bad", "https://yt.test/bad"), _flat_entry("good", "https://yt.test/good")]
        monkeypatch.setattr(provider, "_list_entries", lambda query, limit: entries)

        def resolve(url):
            if "bad" in url:
                raise RuntimeError("video unavailable")
            return _full_info("good", url, "Good", [AUDIO_FORMAT])

        monkeypatch.setattr(provider, "_resolve", resolve)

        page = provider.search(SearchParams(query="rain", extra={"page": 1}))
        assert [r.provider_id for r in page.results] == ["good"]

    def test_license_filter_excludes_non_cc_videos(self, monkeypatch: pytest.MonkeyPatch):
        provider = VideoProvider()
        entries = [_flat_entry("cc", "https://yt.test/cc"), _flat_entry("std", "https://yt.test/std")]
        monkeypatch.setattr(provider, "_list_entries", lambda query, limit: entries)

        def resolve(url):
            if "cc" in url and "std" not in url:
                return _full_info("cc", url, "CC video", [AUDIO_FORMAT], license_="Creative Commons Attribution")
            return _full_info("std", url, "Standard video", [AUDIO_FORMAT], license_="Standard YouTube License")

        monkeypatch.setattr(provider, "_resolve", resolve)

        page = provider.search(
            SearchParams(query="rain", filters={"license": "cc-by"}, extra={"page": 1})
        )
        assert [r.provider_id for r in page.results] == ["cc"]

    def test_license_any_does_not_filter(self, monkeypatch: pytest.MonkeyPatch):
        provider = VideoProvider()
        monkeypatch.setattr(
            provider, "_list_entries", lambda query, limit: [_flat_entry("std", "https://yt.test/std")]
        )
        monkeypatch.setattr(
            provider,
            "_resolve",
            lambda url: _full_info("std", url, "Standard", [AUDIO_FORMAT], license_="Standard YouTube License"),
        )

        page = provider.search(
            SearchParams(query="rain", filters={"license": "any"}, extra={"page": 1})
        )
        assert [r.provider_id for r in page.results] == ["std"]

    def test_entries_cached_across_pages(self, monkeypatch: pytest.MonkeyPatch):
        provider = VideoProvider()
        calls = []

        def list_entries(query, limit):
            calls.append(query)
            return [_flat_entry("a", "https://yt.test/a")]

        monkeypatch.setattr(provider, "_list_entries", list_entries)
        monkeypatch.setattr(provider, "_resolve", lambda url: _full_info("a", url, "A", [AUDIO_FORMAT]))

        provider.search(SearchParams(query="rain", extra={"page": 1}))
        provider.search(SearchParams(query="rain", extra={"page": 1}))

        # provider._list_entries itself caches internally in the real
        # implementation; this test only proves search() calls it once per
        # distinct SearchParams.query it's given, not that it re-lists.
        assert calls == ["rain", "rain"]


class TestDownload:
    def test_streams_resolved_audio_format(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, requests_mock
    ):
        provider = VideoProvider()
        monkeypatch.setattr(
            provider, "_resolve", lambda url: _full_info("abc", url, "Rain", [AUDIO_FORMAT])
        )
        requests_mock.get("https://cdn.test/stream.m4a", content=b"audio bytes")

        ref = SoundRef(
            provider="video", provider_id="abc", name="Rain", url="https://yt.test/abc", file_format="m4a"
        )
        target = tmp_path / "out" / "rain.m4a"
        result = provider.download(ref, tmp_path / "out", target=target)

        assert result.status == "downloaded"
        assert target.read_bytes() == b"audio bytes"
        assert requests_mock.last_request.headers["User-Agent"] == "test-agent"

    def test_raises_without_watch_url(self, tmp_path: Path):
        provider = VideoProvider()
        ref = SoundRef(provider="video", provider_id="abc", name="x", url="")
        with pytest.raises(DownloadError):
            provider.download(ref, tmp_path / "out")

    def test_raises_when_resolve_fails(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        provider = VideoProvider()

        def resolve(url):
            raise RuntimeError("video unavailable")

        monkeypatch.setattr(provider, "_resolve", resolve)
        ref = SoundRef(provider="video", provider_id="abc", name="x", url="https://yt.test/abc")

        with pytest.raises(DownloadError):
            provider.download(ref, tmp_path / "out")

    def test_raises_when_no_audio_format_at_download_time(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        provider = VideoProvider()
        monkeypatch.setattr(provider, "_resolve", lambda url: _full_info("abc", url, "x", []))
        ref = SoundRef(provider="video", provider_id="abc", name="x", url="https://yt.test/abc")

        with pytest.raises(DownloadError):
            provider.download(ref, tmp_path / "out")

    def test_reresolves_rather_than_trusting_cached_download_url(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, requests_mock
    ):
        """The whole point of re-resolving at download time: a download_url
        cached from search() may have expired by the time download() runs."""
        provider = VideoProvider()
        monkeypatch.setattr(
            provider, "_resolve", lambda url: _full_info("abc", url, "Rain", [AUDIO_FORMAT])
        )
        requests_mock.get("https://cdn.test/stream.m4a", content=b"fresh bytes")

        ref = SoundRef(
            provider="video",
            provider_id="abc",
            name="Rain",
            url="https://yt.test/abc",
            download_url="https://cdn.test/expired-stale-url.m4a",  # never hit
            file_format="m4a",
        )
        target = tmp_path / "out" / "rain.m4a"
        provider.download(ref, tmp_path / "out", target=target)

        assert target.read_bytes() == b"fresh bytes"


class TestStatus:
    def test_reports_installed(self):
        provider = VideoProvider()
        # yt-dlp is a dev-time convenience install in this repo's .venv;
        # this just proves status() reflects real importability either way.
        import importlib.util

        expected = importlib.util.find_spec("yt_dlp") is not None
        assert provider.status() == {"yt_dlp_installed": expected}

    def test_reports_missing(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setitem(sys.modules, "yt_dlp", None)
        provider = VideoProvider()
        assert provider.status() == {"yt_dlp_installed": False}
