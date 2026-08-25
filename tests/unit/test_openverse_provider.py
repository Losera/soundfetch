from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from soundfetch.core.downloader import DownloadError
from soundfetch.core.model import SearchParams, SoundRef
from soundfetch.providers.openverse.filters import build_params
from soundfetch.providers.openverse.provider import SEARCH_URL, OpenverseProvider


def _query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


def _item(**overrides):
    item = {
        "id": "8624ba61-57f1-4f98-8a85-ece206c319cf",
        "title": "Rain on roof",
        "foreign_landing_url": "https://freesound.org/s/123/",
        "url": "https://cdn.example.test/rain.wav",
        "creator": "Field Recordist",
        "creator_url": "https://example.test/creator",
        "license": "by-nc-sa",
        "license_version": "4.0",
        "license_url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
        "attribution": "Rain on roof by Field Recordist, CC BY-NC-SA 4.0",
        "provider": "freesound",
        "source": "freesound",
        "category": "sound_effect",
        "duration": 1250,
        "filesize": 1234,
        "filetype": "wav",
        "bit_rate": 1411200,
        "sample_rate": 44100,
        "tags": [{"name": "rain", "accuracy": None}],
        "genres": [],
        "indexed_on": "2026-01-01T00:00:00Z",
        "mature": False,
        "detail_url": "https://api.openverse.org/v1/audio/id/",
    }
    item.update(overrides)
    return item


def _payload(*, results=None, page=1, page_count=1, result_count=None):
    results = [_item()] if results is None else results
    return {
        "result_count": len(results) if result_count is None else result_count,
        "page_count": page_count,
        "page_size": 20,
        "page": page,
        "results": results,
    }


class TestFilters:
    def test_maps_soundfetch_license_codes(self):
        assert build_params({"license": "cc-by,cc-by-nc-sa,pdm"}) == {
            "license": "by,by-nc-sa,pdm"
        }

    def test_any_omits_license(self):
        assert build_params({"license": "any"}) == {}

    def test_stable_filters_are_comma_joined(self):
        assert build_params(
            {
                "category": "sound_effect,music",
                "source": "freesound",
                "extension": "wav,flac",
                "length": "shortest,short",
                "raw": "unstable__sort_by=indexed_on",
            }
        ) == {
            "category": "sound_effect,music",
            "source": "freesound",
            "extension": "wav,flac",
            "length": "shortest,short",
        }


@pytest.fixture
def provider() -> OpenverseProvider:
    provider = OpenverseProvider()
    provider.rate_limiter = type("NoopLimiter", (), {"acquire": lambda self: None})()
    return provider


class TestSearch:
    def test_sends_stable_filters_and_clamps_anonymous_page_size(
        self, provider, requests_mock
    ):
        requests_mock.get(SEARCH_URL, json=_payload(results=[]))
        provider.search(
            SearchParams(
                query="rain",
                page_size=50,
                filters={
                    "license": "cc0,cc-by",
                    "category": "sound_effect",
                    "source": "freesound",
                    "extension": "wav",
                    "length": "short",
                },
                extra={"page": 2},
            )
        )

        query = _query(requests_mock.last_request.url)
        assert query == {
            "q": ["rain"],
            "page": ["2"],
            "page_size": ["20"],
            "filter_dead": ["true"],
            "mature": ["false"],
            "license": ["cc0,by"],
            "category": ["sound_effect"],
            "source": ["freesound"],
            "extension": ["wav"],
            "length": ["short"],
        }

    def test_maps_identity_download_and_provenance(self, provider, requests_mock):
        requests_mock.get(SEARCH_URL, json=_payload())
        ref = provider.search(SearchParams(query="rain")).results[0]

        assert ref.provider == "openverse"
        assert ref.provider_id == "8624ba61-57f1-4f98-8a85-ece206c319cf"
        assert ref.name == "Rain on roof"
        assert ref.url == "https://freesound.org/s/123/"
        assert ref.download_url == "https://cdn.example.test/rain.wav"
        assert ref.file_format == "wav"
        assert ref.metadata["openverse_id"] == ref.provider_id
        assert ref.metadata["provider"] == "freesound"
        assert ref.metadata["source"] == "freesound"
        assert ref.metadata["duration_ms"] == 1250
        assert "duration" not in ref.metadata
        assert ref.metadata["attribution"].startswith("Rain on roof")

    def test_normalizes_openverse_mp32_catalog_label(self, provider, requests_mock):
        requests_mock.get(SEARCH_URL, json=_payload(results=[_item(filetype="mp32")]))
        ref = provider.search(SearchParams(query="music")).results[0]
        assert ref.file_format == "mp3"
        assert ref.metadata["filetype"] == "mp32"

    def test_uses_openverse_page_metadata_for_has_more(self, provider, requests_mock):
        requests_mock.get(
            SEARCH_URL, json=_payload(page=2, page_count=3, result_count=41)
        )
        page = provider.search(SearchParams(query="rain", extra={"page": 2}))
        assert page.total == 41
        assert page.has_more is True

    @pytest.mark.parametrize(
        "item",
        [
            _item(id=None),
            _item(url=None),
            _item(foreign_landing_url=None),
            "not-an-object",
        ],
    )
    def test_skips_results_without_required_identity_or_urls(
        self, provider, requests_mock, item
    ):
        requests_mock.get(SEARCH_URL, json=_payload(results=[item]))
        assert provider.search(SearchParams(query="rain")).results == []

    def test_rejects_malformed_success_response(self, provider, requests_mock):
        requests_mock.get(SEARCH_URL, json={"result_count": 1})
        with pytest.raises(ValueError, match="results list"):
            provider.search(SearchParams(query="rain"))


class TestDownload:
    def test_downloads_direct_url_through_shared_downloader(
        self, provider, requests_mock, tmp_path: Path
    ):
        requests_mock.get("https://cdn.example.test/rain.wav", content=b"audio")
        ref = SoundRef(
            provider="openverse",
            provider_id="id-1",
            name="rain",
            url="https://example.test/work",
            download_url="https://cdn.example.test/rain.wav",
            file_format="wav",
        )

        result = provider.download(ref, tmp_path)

        assert result.status == "downloaded"
        assert result.bytes == 5
        assert result.local_path == tmp_path / "id-1.wav"
        assert result.local_path.read_bytes() == b"audio"

    def test_missing_download_url_is_download_error(self, provider, tmp_path: Path):
        ref = SoundRef(
            provider="openverse",
            provider_id="id-1",
            name="rain",
            url="https://example.test/work",
        )
        with pytest.raises(DownloadError, match="no download URL"):
            provider.download(ref, tmp_path)


def test_status_requires_no_auth(provider):
    assert provider.status() == {"auth_required": False}
