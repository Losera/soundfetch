from __future__ import annotations

from pathlib import Path

import pytest

from soundfetch.core.downloader import DownloadError
from soundfetch.core.engine import download_refs, ref_record, search_all, write_search_records
from soundfetch.core.manifest import iter_latest, read_records
from soundfetch.core.model import SearchParams, SearchPage

from ..fakes import FakeProvider, failing_download, make_ref


# ---------------------------------------------------------------------------
# search_all
# ---------------------------------------------------------------------------


class TestSearchAll:
    def test_pages_until_has_more_is_false(self):
        page1 = SearchPage(results=[make_ref("1"), make_ref("2")], total=3, has_more=True)
        page2 = SearchPage(results=[make_ref("3")], total=3, has_more=False)
        provider = FakeProvider(pages=[page1, page2])

        refs = search_all(provider, SearchParams(query="x"))

        assert [r.provider_id for r in refs] == ["1", "2", "3"]
        assert provider.search_calls == [1, 2]

    def test_single_page_when_has_more_false(self):
        page1 = SearchPage(results=[make_ref("1")], total=1, has_more=False)
        provider = FakeProvider(pages=[page1])

        refs = search_all(provider, SearchParams(query="x"))

        assert [r.provider_id for r in refs] == ["1"]
        assert provider.search_calls == [1]

    def test_stops_and_truncates_at_max_results(self):
        page1 = SearchPage(results=[make_ref("1"), make_ref("2")], total=5, has_more=True)
        page2 = SearchPage(results=[make_ref("3"), make_ref("4")], total=5, has_more=True)
        provider = FakeProvider(pages=[page1, page2])

        refs = search_all(provider, SearchParams(query="x", max_results=3))

        assert [r.provider_id for r in refs] == ["1", "2", "3"]

    def test_on_page_callback_invoked_per_page(self):
        page1 = SearchPage(results=[make_ref("1")], total=2, has_more=True)
        page2 = SearchPage(results=[make_ref("2")], total=2, has_more=False)
        provider = FakeProvider(pages=[page1, page2])
        seen = []

        search_all(provider, SearchParams(query="x"), on_page=lambda result, page: seen.append(page))

        assert seen == [1, 2]

    def test_params_not_mutated_across_pages(self):
        page1 = SearchPage(results=[make_ref("1")], total=1, has_more=False)
        provider = FakeProvider(pages=[page1])
        params = SearchParams(query="x", extra={"page": 1, "with_descriptors": ["bpm"]})

        search_all(provider, params)

        assert params.extra == {"page": 1, "with_descriptors": ["bpm"]}


# ---------------------------------------------------------------------------
# write_search_records
# ---------------------------------------------------------------------------


def test_write_search_records_writes_listed_status(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    refs = [make_ref("1", name="rain"), make_ref("2", name="thunder")]

    write_search_records(manifest, refs, total=2)

    records = read_records(manifest)
    assert len(records) == 2
    assert all(r["status"] == "listed" for r in records)
    assert all(r["error"] is None for r in records)
    assert {r["provider_id"] for r in records} == {"1", "2"}


def test_ref_record_envelope_fields():
    ref = make_ref("1", name="rain", url="https://x/1", checksum="abc")
    record = ref_record(ref)
    assert record == {
        "provider": "fake",
        "provider_id": "1",
        "name": "rain",
        "url": "https://x/1",
        "file_format": "wav",
        "checksum": "abc",
        "download_url": None,
        "metadata": {},
    }


# ---------------------------------------------------------------------------
# download_refs
# ---------------------------------------------------------------------------


class TestDownloadRefs:
    def test_downloads_and_checkpoints_manifest(self, tmp_path: Path):
        dest_dir = tmp_path / "out"
        manifest = tmp_path / "manifest.jsonl"
        provider = FakeProvider()
        refs = [make_ref("1", name="rain")]

        results = download_refs(provider, refs, dest_dir, manifest)

        assert len(results) == 1
        assert results[0].status == "downloaded"
        assert provider.download_calls == ["1"]

        records = list(iter_latest(manifest))
        assert records[0]["status"] == "downloaded"
        assert records[0]["local_file"] == "rain.wav"
        assert (dest_dir / "rain.wav").exists()

    def test_resume_skips_already_downloaded_existing_file(self, tmp_path: Path):
        dest_dir = tmp_path / "out"
        dest_dir.mkdir(parents=True)
        manifest = tmp_path / "manifest.jsonl"
        (dest_dir / "rain.wav").write_bytes(b"cached")

        from soundfetch.core.manifest import append_record

        append_record(
            manifest,
            {
                "provider": "fake",
                "provider_id": "1",
                "status": "downloaded",
                "local_file": "rain.wav",
            },
        )

        provider = FakeProvider()
        refs = [make_ref("1", name="rain")]

        results = download_refs(provider, refs, dest_dir, manifest, resume=True)

        assert results[0].status == "skipped"
        assert provider.download_calls == []  # never re-downloaded

    def test_resume_redownloads_if_local_file_missing(self, tmp_path: Path):
        dest_dir = tmp_path / "out"
        manifest = tmp_path / "manifest.jsonl"

        from soundfetch.core.manifest import append_record

        append_record(
            manifest,
            {
                "provider": "fake",
                "provider_id": "1",
                "status": "downloaded",
                "local_file": "rain.wav",  # not actually on disk
            },
        )

        provider = FakeProvider()
        refs = [make_ref("1", name="rain")]

        results = download_refs(provider, refs, dest_dir, manifest, resume=True)

        assert results[0].status == "downloaded"
        assert provider.download_calls == ["1"]

    def test_overwrite_forces_redownload(self, tmp_path: Path):
        dest_dir = tmp_path / "out"
        dest_dir.mkdir(parents=True)
        manifest = tmp_path / "manifest.jsonl"
        (dest_dir / "rain.wav").write_bytes(b"cached")

        from soundfetch.core.manifest import append_record

        append_record(
            manifest,
            {"provider": "fake", "provider_id": "1", "status": "downloaded", "local_file": "rain.wav"},
        )

        provider = FakeProvider()
        refs = [make_ref("1", name="rain")]

        results = download_refs(provider, refs, dest_dir, manifest, resume=True, overwrite=True)

        assert results[0].status == "downloaded"
        assert provider.download_calls == ["1"]

    def test_fail_fast_raises_and_stops_after_first_error(self, tmp_path: Path):
        dest_dir = tmp_path / "out"
        manifest = tmp_path / "manifest.jsonl"
        provider = FakeProvider(download_fn=failing_download())
        refs = [make_ref("1"), make_ref("2")]

        with pytest.raises(DownloadError):
            download_refs(provider, refs, dest_dir, manifest, fail_fast=True)

        assert provider.download_calls == ["1"]

    def test_continue_on_error_records_error_and_keeps_going(self, tmp_path: Path):
        dest_dir = tmp_path / "out"
        manifest = tmp_path / "manifest.jsonl"

        def download_fn(ref, dest_dir_arg, target):
            if ref.provider_id == "1":
                raise DownloadError("network exploded")
            target.write_bytes(b"ok")
            from soundfetch.core.model import DownloadResult

            return DownloadResult(local_path=target, bytes=2, status="downloaded")

        provider = FakeProvider(download_fn=download_fn)
        refs = [make_ref("1"), make_ref("2")]

        results = download_refs(provider, refs, dest_dir, manifest, fail_fast=False)

        assert provider.download_calls == ["1", "2"]
        assert [r.status for r in results] == ["error", "downloaded"]
        assert results[0].error == "network exploded"

        records = list(iter_latest(manifest))
        by_id = {r["provider_id"]: r for r in records}
        assert by_id["1"]["status"] == "error"
        assert by_id["1"]["error"] == "network exploded"
        assert by_id["2"]["status"] == "downloaded"

    def test_name_collisions_get_unique_suffixes(self, tmp_path: Path):
        dest_dir = tmp_path / "out"
        manifest = tmp_path / "manifest.jsonl"
        provider = FakeProvider()
        refs = [make_ref("1", name="rain"), make_ref("2", name="rain")]

        download_refs(provider, refs, dest_dir, manifest)

        assert (dest_dir / "rain.wav").exists()
        assert (dest_dir / "rain (1).wav").exists()

    def test_rate_delay_sleeps_between_downloads(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        sleeps = []
        monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
        dest_dir = tmp_path / "out"
        manifest = tmp_path / "manifest.jsonl"
        provider = FakeProvider()
        refs = [make_ref("1"), make_ref("2"), make_ref("3")]

        download_refs(provider, refs, dest_dir, manifest, rate_delay=0.5)

        assert sleeps == [0.5, 0.5]  # not before the first download

    def test_no_sleep_when_rate_delay_is_zero(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        sleeps = []
        monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
        dest_dir = tmp_path / "out"
        manifest = tmp_path / "manifest.jsonl"
        provider = FakeProvider()
        refs = [make_ref("1"), make_ref("2")]

        download_refs(provider, refs, dest_dir, manifest, rate_delay=0.0)

        assert sleeps == []
