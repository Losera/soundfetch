from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from soundfetch.core.model import SearchParams
from soundfetch.providers.freesound.filters import build_filter
from soundfetch.providers.freesound.provider import BASE_URL, FreesoundProvider


def _qs(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


# ---------------------------------------------------------------------------
# filters.build_filter
# ---------------------------------------------------------------------------


class TestBuildFilter:
    def test_no_filters_returns_empty_string(self):
        assert build_filter({}) == ""

    def test_single_license(self):
        assert build_filter({"license": "cc0"}) == 'license:("Creative Commons 0")'

    def test_multiple_licenses_or_joined(self):
        result = build_filter({"license": "cc0,cc-by"})
        assert result == 'license:("Creative Commons 0" OR "Attribution")'

    def test_license_any_is_ignored(self):
        assert build_filter({"license": "any"}) == ""

    def test_duration_passthrough(self):
        assert build_filter({"duration": "[1 TO 30]"}) == "duration:[1 TO 30]"

    def test_single_tag(self):
        assert build_filter({"tag": "rain"}) == 'tag:"rain"'

    def test_multiple_tags_or_joined(self):
        assert build_filter({"tag": "rain,storm"}) == 'tag:("rain" OR "storm")'

    def test_gen_ai_valid_value(self):
        assert build_filter({"gen_ai": "deny"}) == 'gen_ai_preference:"deny"'

    def test_gen_ai_any_is_ignored(self):
        assert build_filter({"gen_ai": "any"}) == ""

    def test_gen_ai_invalid_value_raises(self):
        with pytest.raises(ValueError):
            build_filter({"gen_ai": "bogus"})

    def test_raw_passthrough(self):
        assert build_filter({"raw": "channels:1"}) == "channels:1"

    def test_clauses_combined_with_and(self):
        result = build_filter({"license": "cc0", "duration": "[1 TO 30]"})
        assert result == 'license:("Creative Commons 0") AND duration:[1 TO 30]'


# ---------------------------------------------------------------------------
# FreesoundProvider.search
# ---------------------------------------------------------------------------


@pytest.fixture
def provider() -> FreesoundProvider:
    return FreesoundProvider(api_key="test-key")


def _search_payload(**overrides) -> dict:
    payload = {
        "count": 1,
        "next": None,
        "results": [
            {
                "id": 123,
                "name": "Rain on roof.wav",
                "url": "https://freesound.org/s/123/",
                "type": "wav",
                "md5": "abc123",
                "license": "Creative Commons 0",
                "gen_ai_preference": "allow",
                "previews": {
                    "preview-hq-mp3": "https://cdn.test/123-hq.mp3",
                    "preview-lq-mp3": "https://cdn.test/123-lq.mp3",
                    "preview-hq-ogg": "https://cdn.test/123-hq.ogg",
                    "preview-lq-ogg": "https://cdn.test/123-lq.ogg",
                },
            }
        ],
    }
    payload.update(overrides)
    return payload


class TestSearch:
    def test_raises_without_api_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("FREESOUND_API_KEY", raising=False)
        provider = FreesoundProvider(api_key=None)
        with pytest.raises(RuntimeError):
            provider.search(SearchParams(query="piano", extra={"page": 1}))

    def test_sends_query_and_page(self, provider: FreesoundProvider, requests_mock):
        requests_mock.get(f"{BASE_URL}/search/", json=_search_payload())
        provider.search(SearchParams(query="piano", extra={"page": 2}))
        qs = _qs(requests_mock.last_request.url)
        assert qs["query"] == ["piano"]
        assert qs["page"] == ["2"]

    def test_sends_api_key_as_header_not_query_param(
        self, provider: FreesoundProvider, requests_mock
    ):
        """The key must not appear in the URL: a query param ends up in
        server/proxy access logs and in any error message built from the
        request URL (manifest, MCP tool response, CLI --json output)."""
        requests_mock.get(f"{BASE_URL}/search/", json=_search_payload())
        provider.search(SearchParams(query="piano", extra={"page": 1}))
        request = requests_mock.last_request
        assert "token" not in _qs(request.url)
        assert request.headers["Authorization"] == "Token test-key"

    def test_page_size_is_capped_at_150(self, provider: FreesoundProvider, requests_mock):
        requests_mock.get(f"{BASE_URL}/search/", json=_search_payload())
        provider.search(SearchParams(query="piano", page_size=500, extra={"page": 1}))
        qs = _qs(requests_mock.last_request.url)
        assert qs["page_size"] == ["150"]

    def test_filters_are_translated_into_filter_param(self, provider: FreesoundProvider, requests_mock):
        requests_mock.get(f"{BASE_URL}/search/", json=_search_payload())
        provider.search(
            SearchParams(query="piano", filters={"license": "cc0"}, extra={"page": 1})
        )
        qs = _qs(requests_mock.last_request.url)
        assert qs["filter"] == ['license:("Creative Commons 0")']

    def test_no_filter_param_when_no_filters(self, provider: FreesoundProvider, requests_mock):
        requests_mock.get(f"{BASE_URL}/search/", json=_search_payload())
        provider.search(SearchParams(query="piano", extra={"page": 1}))
        qs = _qs(requests_mock.last_request.url)
        assert "filter" not in qs

    def test_sort_passed_through(self, provider: FreesoundProvider, requests_mock):
        requests_mock.get(f"{BASE_URL}/search/", json=_search_payload())
        provider.search(SearchParams(query="piano", sort="duration_desc", extra={"page": 1}))
        qs = _qs(requests_mock.last_request.url)
        assert qs["sort"] == ["duration_desc"]

    def test_descriptors_extend_fields(self, provider: FreesoundProvider, requests_mock):
        requests_mock.get(f"{BASE_URL}/search/", json=_search_payload())
        provider.search(
            SearchParams(query="piano", extra={"page": 1, "with_descriptors": ["bpm", "pitch"]})
        )
        qs = _qs(requests_mock.last_request.url)
        assert "bpm" in qs["fields"][0]
        assert "pitch" in qs["fields"][0]

    def test_has_more_true_when_next_present(self, provider: FreesoundProvider, requests_mock):
        requests_mock.get(
            f"{BASE_URL}/search/", json=_search_payload(next="https://freesound.org/apiv2/search/?page=2")
        )
        page = provider.search(SearchParams(query="piano", extra={"page": 1}))
        assert page.has_more is True
        assert page.total == 1

    def test_has_more_false_when_next_is_null(self, provider: FreesoundProvider, requests_mock):
        requests_mock.get(f"{BASE_URL}/search/", json=_search_payload(next=None))
        page = provider.search(SearchParams(query="piano", extra={"page": 1}))
        assert page.has_more is False

    def test_ref_conversion_picks_configured_preview_and_metadata(
        self, provider: FreesoundProvider, requests_mock
    ):
        requests_mock.get(f"{BASE_URL}/search/", json=_search_payload())
        page = provider.search(SearchParams(query="piano", extra={"page": 1}))
        ref = page.results[0]
        assert ref.provider == "freesound"
        assert ref.provider_id == "123"
        assert ref.name == "Rain on roof.wav"
        assert ref.download_url == "https://cdn.test/123-hq.mp3"  # default hq/mp3
        assert ref.file_format == "wav"  # metadata "type" wins over preview_format
        assert ref.checksum == "abc123"
        assert ref.metadata["license"] == "Creative Commons 0"

    def test_ref_conversion_respects_quality_and_format(self, requests_mock):
        provider = FreesoundProvider(api_key="test-key", preview_quality="lq", preview_format="ogg")
        requests_mock.get(f"{BASE_URL}/search/", json=_search_payload())
        page = provider.search(SearchParams(query="piano", extra={"page": 1}))
        assert page.results[0].download_url == "https://cdn.test/123-lq.ogg"


# ---------------------------------------------------------------------------
# FreesoundProvider.download
# ---------------------------------------------------------------------------


class TestDownload:
    def test_preview_download_writes_file(self, requests_mock, tmp_path: Path):
        provider = FreesoundProvider(api_key="test-key", mode="preview")
        requests_mock.get(f"{BASE_URL}/search/", json=_search_payload())
        ref = provider.search(SearchParams(query="piano", extra={"page": 1})).results[0]

        requests_mock.get("https://cdn.test/123-hq.mp3", content=b"mp3 bytes")
        target = tmp_path / "out" / "rain.mp3"
        result = provider.download(ref, tmp_path / "out", target=target)

        assert result.status == "downloaded"
        assert target.read_bytes() == b"mp3 bytes"

    def test_preview_download_without_url_raises(self, provider: FreesoundProvider, tmp_path: Path):
        from soundfetch.core.downloader import DownloadError
        from soundfetch.core.model import SoundRef

        ref = SoundRef(provider="freesound", provider_id="1", name="x", metadata={})
        with pytest.raises(DownloadError):
            provider.download(ref, tmp_path / "out")

    def test_original_download_sends_bearer_token(
        self, requests_mock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        from soundfetch.core.model import SoundRef

        provider = FreesoundProvider(api_key="test-key", mode="original")
        monkeypatch.setattr(provider, "_bearer_token", lambda: "TOK123")

        content = b"lossless wav bytes"
        checksum = hashlib.md5(content).hexdigest()

        def callback(request, context):
            assert request.headers["Authorization"] == "Bearer TOK123"
            return content

        requests_mock.get(f"{BASE_URL}/sounds/123/download/", content=callback)

        ref = SoundRef(
            provider="freesound", provider_id="123", name="rain", file_format="wav", checksum=checksum
        )
        target = tmp_path / "out" / "rain.wav"
        result = provider.download(ref, tmp_path / "out", target=target)

        assert result.status == "downloaded"
        assert target.read_bytes() == content


# ---------------------------------------------------------------------------
# FreesoundProvider.status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_reports_missing_when_nothing_configured(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("FREESOUND_API_KEY", raising=False)
        monkeypatch.delenv("FREESOUND_CLIENT_ID", raising=False)
        monkeypatch.delenv("FREESOUND_CLIENT_SECRET", raising=False)
        provider = FreesoundProvider(api_key=None)
        status = provider.status()
        assert status == {
            "api_key": False,
            "client_id": False,
            "client_secret": False,
            "oauth_token": False,
            "oauth_token_expired": False,
        }

    def test_reports_configured_api_key(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("FREESOUND_CLIENT_ID", raising=False)
        monkeypatch.delenv("FREESOUND_CLIENT_SECRET", raising=False)
        provider = FreesoundProvider(api_key="test-key")
        assert provider.status()["api_key"] is True

    def test_oauth_token_true_when_cached_token_present(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        monkeypatch.setenv("FREESOUND_CLIENT_ID", "cid")
        monkeypatch.setenv("FREESOUND_CLIENT_SECRET", "csecret")
        token_path = tmp_path / "freesound.json"
        token_path.write_text(
            json.dumps({"access_token": "tok", "expires_at": 9999999999.0, "scope": ""})
        )
        provider = FreesoundProvider(api_key="test-key", config_dir=tmp_path)
        status = provider.status()
        assert status["client_id"] is True
        assert status["client_secret"] is True
        assert status["oauth_token"] is True

    def test_oauth_token_false_when_no_cached_token(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        monkeypatch.setenv("FREESOUND_CLIENT_ID", "cid")
        monkeypatch.setenv("FREESOUND_CLIENT_SECRET", "csecret")
        provider = FreesoundProvider(api_key="test-key", config_dir=tmp_path)
        assert provider.status()["oauth_token"] is False


def test_invalid_mode_raises():
    with pytest.raises(ValueError):
        FreesoundProvider(api_key="k", mode="bogus")


def test_invalid_preview_format_raises():
    with pytest.raises(ValueError):
        FreesoundProvider(api_key="k", preview_format="wav")
