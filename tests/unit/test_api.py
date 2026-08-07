"""Tests for the public Python API (soundfetch.api)."""

from __future__ import annotations

from pathlib import Path

import pytest

import soundfetch.api as api
from soundfetch.api import (
    download,
    refs_from_manifest,
    save_search,
    search,
)
from soundfetch.core.manifest import append_record
from soundfetch.core.model import SearchPage, SoundRef

from ..fakes import FakeProvider, make_ref


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


class TestSearch:
    def test_returns_refs_from_provider(self):
        page = SearchPage(results=[make_ref("1"), make_ref("2")], total=2, has_more=False)
        fake = FakeProvider(pages=[page])
        refs = search("rain", providers={"freesound": fake})

        assert len(refs) == 2
        assert refs[0].provider_id == "1"

    def test_builds_filters_dict(self):
        page = SearchPage(results=[], total=0, has_more=False)
        fake = FakeProvider(pages=[page])
        search(
            "rain",
            providers={"freesound": fake},
            license="cc0",
            duration="[1 TO 30]",
            tag="thunder",
            gen_ai="deny",
            raw_filter="samplerate:[44100 TO *]",
        )
        params = fake.search_params[0]
        assert params.filters == {
            "license": "cc0",
            "duration": "[1 TO 30]",
            "tag": "thunder",
            "gen_ai": "deny",
            "raw": "samplerate:[44100 TO *]",
        }

    def test_tuple_license_joins_to_comma_string(self):
        page = SearchPage(results=[], total=0, has_more=False)
        fake = FakeProvider(pages=[page])
        search("rain", providers={"freesound": fake}, license=("cc0", "cc-by"))
        params = fake.search_params[0]
        assert params.filters["license"] == "cc0,cc-by"

    def test_on_page_callback_called(self):
        page = SearchPage(results=[make_ref("1")], total=1, has_more=False)
        fake = FakeProvider(pages=[page])
        calls = []
        search("rain", providers={"freesound": fake}, on_page=lambda r, p: calls.append(p))
        assert calls == [1]

    def test_max_results_truncates(self):
        page1 = SearchPage(results=[make_ref("1"), make_ref("2")], total=5, has_more=True)
        page2 = SearchPage(results=[make_ref("3")], total=5, has_more=False)
        fake = FakeProvider(pages=[page1, page2])
        refs = search("rain", providers={"freesound": fake}, max_results=2)
        assert [r.provider_id for r in refs] == ["1", "2"]


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------


class TestDownload:
    def test_groups_refs_by_provider(self, tmp_path: Path):
        ref_a = SoundRef(provider="alpha", provider_id="a1", name="rain", url="x", file_format="wav")
        ref_b = SoundRef(provider="beta", provider_id="b1", name="thunder", url="x", file_format="wav")
        alpha = FakeProvider()
        beta = FakeProvider()

        results = download(
            [ref_a, ref_b],
            dest_dir=tmp_path,
            providers={"alpha": alpha, "beta": beta},
        )

        assert alpha.download_calls == ["a1"]
        assert beta.download_calls == ["b1"]
        assert len(results) == 2

    def test_empty_refs_returns_empty(self):
        assert download([], dest_dir=Path("/tmp/x")) == []

    def test_writes_manifest(self, tmp_path: Path):
        ref = SoundRef(provider="fake", provider_id="1", name="rain", url="x", file_format="wav")
        fake = FakeProvider()

        download(
            [ref],
            dest_dir=tmp_path / "out",
            manifest=tmp_path / "out" / "manifest.jsonl",
            providers={"fake": fake},
        )

        manifest = tmp_path / "out" / "manifest.jsonl"
        assert manifest.exists()
        assert fake.download_calls == ["1"]

    def test_resume_true_skips_already_downloaded(self, tmp_path: Path):
        dest_dir = tmp_path / "out"
        dest_dir.mkdir()
        (dest_dir / "rain.wav").write_bytes(b"cached")
        manifest = tmp_path / "manifest.jsonl"
        append_record(
            manifest,
            {
                "provider": "fake",
                "provider_id": "1",
                "status": "downloaded",
                "local_file": "rain.wav",
            },
        )
        ref = SoundRef(provider="fake", provider_id="1", name="rain", url="x", file_format="wav")
        fake = FakeProvider()

        results = download(
            [ref], dest_dir=dest_dir, manifest=manifest, providers={"fake": fake}
        )

        assert results[0].status == "skipped"
        assert fake.download_calls == []


# ---------------------------------------------------------------------------
# save_search / refs_from_manifest round-trip
# ---------------------------------------------------------------------------


class TestManifestRoundTrip:
    def test_save_search_writes_listed_records(self, tmp_path: Path):
        manifest = tmp_path / "manifest.jsonl"
        refs = [make_ref("1", name="rain"), make_ref("2", name="thunder")]

        save_search(refs, manifest)

        import json

        lines = manifest.read_text().strip().splitlines()
        assert len(lines) == 2
        rec = json.loads(lines[0])
        assert rec["status"] == "listed"
        assert rec["provider_id"] in ("1", "2")

    def test_refs_from_manifest_builds_refs_for_listed(self, tmp_path: Path):
        manifest = tmp_path / "manifest.jsonl"
        append_record(
            manifest,
            {
                "provider": "archive",
                "provider_id": "1",
                "name": "rain",
                "url": "https://example.test/1",
                "file_format": "wav",
                "status": "listed",
            },
        )

        refs = refs_from_manifest(manifest)

        assert len(refs) == 1
        assert refs[0].provider_id == "1"
        assert refs[0].name == "rain"

    def test_refs_from_manifest_skips_downloaded(self, tmp_path: Path):
        manifest = tmp_path / "manifest.jsonl"
        append_record(
            manifest,
            {
                "provider": "archive",
                "provider_id": "1",
                "name": "rain",
                "status": "downloaded",
                "local_file": "rain.wav",
            },
        )

        assert refs_from_manifest(manifest) == []

    def test_refs_from_manifest_returns_empty_for_missing_file(self, tmp_path: Path):
        """refs_from_manifest should handle a manifest that doesn't exist yet."""
        assert refs_from_manifest(tmp_path / "nope.jsonl") == []
