from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

import soundfetch.cli as cli_module
from soundfetch.cli import _refs_from_manifest, main
from soundfetch.core.manifest import append_record
from soundfetch.core.model import SearchPage

from ..fakes import FakeProvider, make_ref


def test_sources_lists_registered_providers():
    result = CliRunner().invoke(main, ["sources"])
    assert result.exit_code == 0
    assert "archive" in result.output
    assert "freesound" in result.output


class TestRefsFromManifest:
    """Regression coverage: this helper used to reference SoundRef without
    importing it, so any --manifest download with a non-downloaded entry
    crashed with NameError. See core.engine's DownloadResult fix for the
    sibling bug this shipped alongside."""

    def test_builds_refs_for_listed_records(self, tmp_path: Path):
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

        refs = _refs_from_manifest(manifest)

        assert len(refs) == 1
        assert refs[0].provider_id == "1"
        assert refs[0].name == "rain"
        assert refs[0].file_format == "wav"

    def test_skips_already_downloaded_records(self, tmp_path: Path):
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

        assert _refs_from_manifest(manifest) == []


class TestArchiveCli:
    def test_search_writes_manifest(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        page = SearchPage(results=[make_ref("1", name="rain")], total=1, has_more=False)
        fake = FakeProvider(pages=[page])
        monkeypatch.setattr(cli_module, "_archive_provider", lambda: fake)

        outdir = tmp_path / "out"
        result = CliRunner().invoke(main, ["archive", "search", "rain", "-o", str(outdir)])

        assert result.exit_code == 0, result.output
        assert (outdir / "manifest.jsonl").exists()

    def test_download_from_manifest_end_to_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        fake = FakeProvider()
        monkeypatch.setattr(cli_module, "_archive_provider", lambda: fake)

        outdir = tmp_path / "out"
        manifest = outdir / "manifest.jsonl"
        append_record(
            manifest,
            {
                "provider": "fake",
                "provider_id": "1",
                "name": "rain",
                "file_format": "wav",
                "status": "listed",
            },
        )

        result = CliRunner().invoke(
            main, ["archive", "download", "--manifest", str(manifest), "-o", str(outdir)]
        )

        assert result.exit_code == 0, result.output
        assert fake.download_calls == ["1"]
        assert "downloaded=1" in result.output

    def test_status_reports_no_auth_required(self):
        result = CliRunner().invoke(main, ["archive", "status"])
        assert result.exit_code == 0
        assert "no auth" in result.output


class TestFreesoundCli:
    def test_download_from_manifest_end_to_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        fake = FakeProvider()
        monkeypatch.setattr(
            cli_module, "_freesound_provider", lambda mode, quality, fmt: fake
        )

        outdir = tmp_path / "out"
        manifest = outdir / "manifest.jsonl"
        append_record(
            manifest,
            {
                "provider": "fake",
                "provider_id": "1",
                "name": "rain",
                "file_format": "wav",
                "status": "listed",
            },
        )

        result = CliRunner().invoke(
            main, ["freesound", "download", "--manifest", str(manifest), "-o", str(outdir)]
        )

        assert result.exit_code == 0, result.output
        assert fake.download_calls == ["1"]

    def test_status_reports_missing_without_env(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("FREESOUND_API_KEY", raising=False)
        monkeypatch.delenv("FREESOUND_CLIENT_ID", raising=False)
        monkeypatch.delenv("FREESOUND_CLIENT_SECRET", raising=False)

        result = CliRunner().invoke(main, ["freesound", "status"])

        assert result.exit_code == 0
        assert "api_key: missing" in result.output

    def test_download_requires_query_or_manifest(self):
        result = CliRunner().invoke(main, ["freesound", "download"])
        assert result.exit_code != 0
        assert "QUERY or --manifest" in result.output


class TestVideoCli:
    def test_search_writes_manifest(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        page = SearchPage(results=[make_ref("abc", name="Rain")], total=1, has_more=False)
        fake = FakeProvider(pages=[page])
        monkeypatch.setattr(cli_module, "_video_provider", lambda: fake)

        outdir = tmp_path / "out"
        result = CliRunner().invoke(main, ["video", "search", "rain ambience", "-o", str(outdir)])

        assert result.exit_code == 0, result.output
        assert (outdir / "manifest.jsonl").exists()

    def test_download_from_manifest_end_to_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        fake = FakeProvider()
        monkeypatch.setattr(cli_module, "_video_provider", lambda: fake)

        outdir = tmp_path / "out"
        manifest = outdir / "manifest.jsonl"
        append_record(
            manifest,
            {
                "provider": "fake",
                "provider_id": "abc",
                "name": "Rain",
                "file_format": "m4a",
                "status": "listed",
            },
        )

        result = CliRunner().invoke(
            main, ["video", "download", "--manifest", str(manifest), "-o", str(outdir)]
        )

        assert result.exit_code == 0, result.output
        assert fake.download_calls == ["abc"]

    def test_status_reports_yt_dlp_installed_or_missing(self):
        result = CliRunner().invoke(main, ["video", "status"])
        assert result.exit_code == 0
        assert "yt_dlp:" in result.output
