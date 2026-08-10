"""Tests for the parallel (workers > 1) download path in core.engine."""

from __future__ import annotations

from pathlib import Path

from ..fakes import FakeProvider, make_ref

from soundfetch.core.downloader import DownloadError
from soundfetch.core.engine import download_refs
from soundfetch.core.manifest import iter_latest


class TestParallelDownloads:
    def test_parallel_downloads_all_refs_in_order(self, tmp_path: Path):
        dest_dir = tmp_path / "out"
        manifest = tmp_path / "manifest.jsonl"
        provider = FakeProvider()
        refs = [make_ref(str(i), name=f"sound-{i}") for i in range(5)]

        results = download_refs(provider, refs, dest_dir, manifest, workers=2)

        # Results mirror input order.
        assert [r.status for r in results] == ["downloaded"] * 5
        # Every ref downloaded exactly once (order is thread-schedule).
        assert sorted(provider.download_calls) == [str(i) for i in range(5)]
        # One file per ref on disk.
        assert len(list(dest_dir.iterdir())) == 5

    def test_parallel_collision_names_get_unique_suffixes(self, tmp_path: Path):
        dest_dir = tmp_path / "out"
        manifest = tmp_path / "manifest.jsonl"
        provider = FakeProvider()
        # All the same name → every file must survive collision handling.
        refs = [make_ref(str(i), name="rain") for i in range(6)]

        results = download_refs(provider, refs, dest_dir, manifest, workers=2)

        assert len(results) == 6
        names = sorted(p.name for p in dest_dir.iterdir())
        assert len(names) == len(set(names)) == 6  # rain.wav, rain (1).wav, ...

    def test_parallel_manifest_records_complete(self, tmp_path: Path):
        dest_dir = tmp_path / "out"
        manifest = tmp_path / "manifest.jsonl"
        provider = FakeProvider()
        refs = [make_ref(str(i)) for i in range(4)]

        download_refs(provider, refs, dest_dir, manifest, workers=2)

        records = {r["provider_id"]: r for r in iter_latest(manifest)}
        assert len(records) == 4
        assert all(r["status"] == "downloaded" for r in records.values())

    def test_parallel_resume_skips_downloaded(self, tmp_path: Path):
        dest_dir = tmp_path / "out"
        dest_dir.mkdir()
        manifest = tmp_path / "manifest.jsonl"
        provider = FakeProvider()
        # First run: download 2.
        download_refs(provider, [make_ref("1"), make_ref("2")], dest_dir, manifest, workers=2)
        # Second run with resume: nothing new to download (files exist).
        refs = [make_ref("1"), make_ref("2")]
        results = download_refs(provider, refs, dest_dir, manifest, workers=2, resume=True)

        assert [r.status for r in results] == ["skipped", "skipped"]

    def test_parallel_continue_on_error(self, tmp_path: Path):
        dest_dir = tmp_path / "out"
        manifest = tmp_path / "manifest.jsonl"

        def download_fn(ref, dest_dir_arg, target):
            if ref.provider_id == "1":
                raise DownloadError("network exploded")
            target.write_bytes(b"ok")
            from soundfetch.core.model import DownloadResult

            return DownloadResult(local_path=target, bytes=2, status="downloaded")

        provider = FakeProvider(download_fn=download_fn)
        refs = [make_ref("1"), make_ref("2"), make_ref("3")]

        results = download_refs(provider, refs, dest_dir, manifest, workers=2, fail_fast=False)

        statuses = sorted(r.status for r in results)
        assert statuses == ["downloaded", "downloaded", "error"]
        # Error still checkpointed to the manifest.
        records = {r["provider_id"]: r for r in iter_latest(manifest)}
        assert records["1"]["status"] == "error"