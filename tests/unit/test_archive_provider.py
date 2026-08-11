from __future__ import annotations

import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from soundfetch.core.model import SearchParams
from soundfetch.providers.archive.filters import build_query
from soundfetch.providers.archive.provider import METADATA_URL, SEARCH_URL, ArchiveProvider


def _qs(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


# ---------------------------------------------------------------------------
# filters.build_query
# ---------------------------------------------------------------------------


class TestBuildQuery:
    def test_wraps_query_and_always_ands_in_mediatype_audio(self):
        assert build_query("piano", {}) == "(piano) AND mediatype:(audio) AND NOT access-restricted-item:true"

    def test_empty_query_still_filters_to_audio(self):
        assert build_query("", {}) == "mediatype:(audio) AND NOT access-restricted-item:true"

    def test_single_license(self):
        result = build_query("piano", {"license": "cc0"})
        assert result == "(piano) AND mediatype:(audio) AND NOT access-restricted-item:true AND (licenseurl:(*publicdomain* OR *cc0*))"

    def test_multiple_licenses_or_joined(self):
        result = build_query("piano", {"license": "cc0,cc-by"})
        assert "licenseurl:(*publicdomain* OR *cc0*)" in result
        assert "licenseurl:*licenses/by/*" in result
        assert " OR " in result.split("(", 2)[-1]

    def test_license_any_is_ignored(self):
        assert build_query("piano", {"license": "any"}) == "(piano) AND mediatype:(audio) AND NOT access-restricted-item:true"

    def test_single_tag_maps_to_subject(self):
        result = build_query("piano", {"tag": "jazz"})
        assert result == '(piano) AND mediatype:(audio) AND NOT access-restricted-item:true AND subject:("jazz")'

    def test_multiple_tags_or_joined(self):
        result = build_query("piano", {"tag": "jazz,blues"})
        assert result == '(piano) AND mediatype:(audio) AND NOT access-restricted-item:true AND subject:("jazz" OR "blues")'

    def test_raw_passthrough(self):
        result = build_query("piano", {"raw": "collection:opensource_audio"})
        assert result.endswith("AND collection:opensource_audio")


# ---------------------------------------------------------------------------
# ArchiveProvider.search
# ---------------------------------------------------------------------------


def _search_payload(docs=None, num_found=None, start=0):
    docs = docs if docs is not None else [{"identifier": "item1", "title": "Rain on roof"}]
    return {
        "response": {
            "numFound": num_found if num_found is not None else len(docs),
            "start": start,
            "docs": docs,
        }
    }


def _metadata_payload(files):
    return {"files": files}


@pytest.fixture
def provider() -> ArchiveProvider:
    return ArchiveProvider()


class TestSearch:
    def test_sends_query_page_and_rows(self, provider: ArchiveProvider, requests_mock):
        requests_mock.get(SEARCH_URL, json=_search_payload(docs=[]))
        provider.search(SearchParams(query="piano", page_size=25, extra={"page": 2}))
        qs = _qs(requests_mock.last_request.url)
        assert qs["q"] == ["(piano) AND mediatype:(audio) AND NOT access-restricted-item:true"]
        assert qs["page"] == ["2"]
        assert qs["rows"] == ["25"]
        assert qs["output"] == ["json"]

    def test_sort_passed_through(self, provider: ArchiveProvider, requests_mock):
        requests_mock.get(SEARCH_URL, json=_search_payload(docs=[]))
        provider.search(SearchParams(query="piano", sort="downloads desc", extra={"page": 1}))
        qs = _qs(requests_mock.last_request.url)
        assert qs["sort[]"] == ["downloads desc"]

    def test_has_more_true_when_more_pages_remain(self, provider: ArchiveProvider, requests_mock):
        requests_mock.get(SEARCH_URL, json=_search_payload(docs=[], num_found=100, start=0))
        page = provider.search(SearchParams(query="piano", extra={"page": 1}))
        assert page.has_more is True
        assert page.total == 100

    def test_has_more_false_when_last_page(self, provider: ArchiveProvider, requests_mock):
        requests_mock.get(
            SEARCH_URL,
            json=_search_payload(
                docs=[{"identifier": "item1", "title": "x"}], num_found=1, start=0
            ),
        )
        requests_mock.get(
            METADATA_URL.format(identifier="item1"),
            json=_metadata_payload([{"name": "item1.mp3", "source": "original", "md5": "abc"}]),
        )
        page = provider.search(SearchParams(query="piano", extra={"page": 1}))
        assert page.has_more is False

    def test_ref_conversion_resolves_audio_file_via_metadata(
        self, provider: ArchiveProvider, requests_mock
    ):
        requests_mock.get(
            SEARCH_URL,
            json=_search_payload(docs=[{"identifier": "item1", "title": "Rain on roof"}]),
        )
        requests_mock.get(
            METADATA_URL.format(identifier="item1"),
            json=_metadata_payload(
                [
                    {"name": "item1.mp3", "source": "derivative", "md5": "mp3md5"},
                    {"name": "item1.jpg", "source": "original", "md5": "coverart"},
                    {"name": "item1.wav", "source": "original", "md5": "wavmd5"},
                ]
            ),
        )
        page = provider.search(SearchParams(query="piano", extra={"page": 1}))
        ref = page.results[0]

        assert ref.provider == "archive"
        assert ref.provider_id == "item1"
        assert ref.name == "Rain on roof"
        assert ref.url == "https://archive.org/details/item1"
        # original wav beats derivative mp3, and non-audio jpg is excluded
        assert ref.file_format == "wav"
        assert ref.checksum == "wavmd5"
        assert ref.download_url == "https://archive.org/download/item1/item1.wav"
        assert ref.metadata["filename"] == "item1.wav"

    def test_prefers_best_extension_when_all_derivative(
        self, provider: ArchiveProvider, requests_mock
    ):
        requests_mock.get(
            SEARCH_URL, json=_search_payload(docs=[{"identifier": "item1", "title": "x"}])
        )
        requests_mock.get(
            METADATA_URL.format(identifier="item1"),
            json=_metadata_payload(
                [
                    {"name": "item1.mp3", "source": "derivative", "md5": "mp3md5"},
                    {"name": "item1.flac", "source": "derivative", "md5": "flacmd5"},
                    {"name": "item1.ogg", "source": "derivative", "md5": "oggmd5"},
                ]
            ),
        )
        page = provider.search(SearchParams(query="x", extra={"page": 1}))
        assert page.results[0].file_format == "flac"

    def test_item_with_no_audio_files_is_skipped(self, provider: ArchiveProvider, requests_mock):
        requests_mock.get(
            SEARCH_URL, json=_search_payload(docs=[{"identifier": "item1", "title": "x"}])
        )
        requests_mock.get(
            METADATA_URL.format(identifier="item1"),
            json=_metadata_payload([{"name": "item1.jpg", "source": "original", "md5": "x"}]),
        )
        page = provider.search(SearchParams(query="x", extra={"page": 1}))
        assert page.results == []

    def test_missing_title_falls_back_to_identifier(self, provider: ArchiveProvider, requests_mock):
        requests_mock.get(
            SEARCH_URL, json=_search_payload(docs=[{"identifier": "item1"}])
        )
        requests_mock.get(
            METADATA_URL.format(identifier="item1"),
            json=_metadata_payload([{"name": "item1.mp3", "source": "original", "md5": "x"}]),
        )
        page = provider.search(SearchParams(query="x", extra={"page": 1}))
        assert page.results[0].name == "item1"

    def test_sequential_progress_includes_skipped_items(self, requests_mock, monkeypatch):
        provider = ArchiveProvider(metadata_workers=1)
        docs = [{"identifier": str(i)} for i in range(3)]
        requests_mock.get(SEARCH_URL, json=_search_payload(docs=docs))
        refs = [object(), None, object()]
        monkeypatch.setattr(provider, "_to_ref", lambda doc: refs[int(doc["identifier"])])
        calls = []

        page = provider.search(
            SearchParams(query="x"), progress=lambda completed, total: calls.append(
                (completed, total)
            )
        )

        assert calls == [(1, 3), (2, 3), (3, 3)]
        assert page.results == [refs[0], refs[2]]

    def test_threaded_progress_is_ordered_and_runs_on_main_thread(
        self, requests_mock, monkeypatch
    ):
        provider = ArchiveProvider(metadata_workers=3)
        docs = [{"identifier": str(i)} for i in range(3)]
        requests_mock.get(SEARCH_URL, json=_search_payload(docs=docs))
        main_thread = threading.current_thread()

        def to_ref(doc):
            time.sleep((2 - int(doc["identifier"])) * 0.01)
            return doc["identifier"]

        monkeypatch.setattr(provider, "_to_ref", to_ref)
        calls = []

        page = provider.search(
            SearchParams(query="x"),
            progress=lambda completed, total: calls.append(
                (completed, total, threading.current_thread())
            ),
        )

        assert page.results == ["0", "1", "2"]
        assert [(completed, total) for completed, total, _ in calls] == [
            (1, 3), (2, 3), (3, 3)
        ]
        assert all(thread is main_thread for _, _, thread in calls)

    def test_empty_page_emits_no_progress(self, provider, requests_mock):
        requests_mock.get(SEARCH_URL, json=_search_payload(docs=[]))
        calls = []

        page = provider.search(
            SearchParams(query="x"),
            progress=lambda completed, total: calls.append((completed, total)),
        )

        assert page.results == []
        assert calls == []

    @pytest.mark.parametrize("workers", [1, 2])
    def test_progress_exception_propagates(
        self, workers, requests_mock, monkeypatch
    ):
        provider = ArchiveProvider(metadata_workers=workers)
        docs = [{"identifier": "0"}, {"identifier": "1"}]
        requests_mock.get(SEARCH_URL, json=_search_payload(docs=docs))
        monkeypatch.setattr(provider, "_to_ref", lambda doc: doc)

        with pytest.raises(RuntimeError, match="caller failed"):
            provider.search(
                SearchParams(query="x"),
                progress=lambda completed, total: (_ for _ in ()).throw(
                    RuntimeError("caller failed")
                ),
            )


# ---------------------------------------------------------------------------
# ArchiveProvider.download
# ---------------------------------------------------------------------------


class TestDownload:
    def test_downloads_via_download_url(self, provider: ArchiveProvider, requests_mock, tmp_path: Path):
        from soundfetch.core.model import SoundRef

        requests_mock.get("https://archive.org/download/item1/item1.wav", content=b"wav bytes")
        ref = SoundRef(
            provider="archive",
            provider_id="item1",
            name="Rain",
            download_url="https://archive.org/download/item1/item1.wav",
            file_format="wav",
        )
        target = tmp_path / "out" / "rain.wav"
        result = provider.download(ref, tmp_path / "out", target=target)

        assert result.status == "downloaded"
        assert target.read_bytes() == b"wav bytes"

    def test_raises_without_download_url(self, provider: ArchiveProvider, tmp_path: Path):
        from soundfetch.core.downloader import DownloadError
        from soundfetch.core.model import SoundRef

        ref = SoundRef(provider="archive", provider_id="item1", name="Rain")
        with pytest.raises(DownloadError):
            provider.download(ref, tmp_path / "out")


def test_status_reports_no_auth_required(provider: ArchiveProvider):
    assert provider.status() == {"auth_required": False}
