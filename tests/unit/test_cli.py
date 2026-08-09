"""Tests for the spec-driven CLI (soundfetch.cli).

Monkeypatch seams use ``monkeypatch.setitem(cli_module.SPECS, ...)``
so command callbacks resolve the patched spec at call time (not import time).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from click.testing import CliRunner

import soundfetch.cli as cli_module
from soundfetch.cli import main, SPECS
from soundfetch.core.manifest import append_record
from soundfetch.core.model import SearchPage

from ..fakes import FakeProvider, make_ref


def test_sources_lists_registered_providers():
    result = CliRunner().invoke(main, ["sources"])
    assert result.exit_code == 0
    assert "archive" in result.output
    assert "freesound" in result.output


# ---------------------------------------------------------------------------
# Archive CLI
# ---------------------------------------------------------------------------


class TestArchiveCli:
    def _patch_spec(self, monkeypatch, fake: FakeProvider):
        original = SPECS["archive"]
        patched = replace(original, build=lambda **kw: fake)
        monkeypatch.setitem(cli_module.SPECS, "archive", patched)

    def test_search_writes_manifest(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        page = SearchPage(results=[make_ref("1", name="rain")], total=1, has_more=False)
        fake = FakeProvider(pages=[page])
        self._patch_spec(monkeypatch, fake)

        outdir = tmp_path / "out"
        result = CliRunner().invoke(main, ["archive", "search", "rain", "-o", str(outdir)])

        assert result.exit_code == 0, result.output
        assert (outdir / "manifest.jsonl").exists()

    def test_download_from_manifest_end_to_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        fake = FakeProvider()
        self._patch_spec(monkeypatch, fake)

        outdir = tmp_path / "out"
        manifest = outdir / "manifest.jsonl"
        append_record(
            manifest,
            {
                "provider": "archive",
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

    def test_download_with_workers_parallel(self, tmp_path, monkeypatch):
        """--workers > 1 downloads every ref (completion order is parallel)."""
        fake = FakeProvider()
        self._patch_spec(monkeypatch, fake)

        outdir = tmp_path / "out"
        manifest = outdir / "manifest.jsonl"
        for i in range(4):
            append_record(
                manifest,
                {
                    "provider": "archive",
                    "provider_id": str(i),
                    "name": f"rain-{i}",
                    "file_format": "wav",
                    "status": "listed",
                },
            )

        result = CliRunner().invoke(
            main,
            [
                "archive", "download",
                "--manifest", str(manifest), "-o", str(outdir),
                "--workers", "2",
            ],
        )

        assert result.exit_code == 0, result.output
        assert sorted(fake.download_calls) == ["0", "1", "2", "3"]
        assert "downloaded=4" in result.output

    def test_download_with_rate_pacing(self, tmp_path, monkeypatch):
        """--rate wires a token-bucket Pacing into the download run."""
        fake = FakeProvider()
        self._patch_spec(monkeypatch, fake)

        outdir = tmp_path / "out"
        manifest = outdir / "manifest.jsonl"
        append_record(
            manifest,
            {
                "provider": "archive",
                "provider_id": "1",
                "name": "rain",
                "file_format": "wav",
                "status": "listed",
            },
        )

        result = CliRunner().invoke(
            main,
            [
                "archive", "download",
                "--manifest", str(manifest), "-o", str(outdir),
                "--rate", "10",
            ],
        )

        assert result.exit_code == 0, result.output
        assert fake.download_calls == ["1"]
        assert "downloaded=1" in result.output

    def test_status_reports_no_auth_required(self):
        result = CliRunner().invoke(main, ["archive", "status"])
        assert result.exit_code == 0
        assert "no configuration required" in result.output


# ---------------------------------------------------------------------------
# Freesound CLI
# ---------------------------------------------------------------------------


class TestFreesoundCli:
    def _patch_spec(self, monkeypatch, fake: FakeProvider):
        original = SPECS["freesound"]
        patched = replace(original, build=lambda **kw: fake)
        monkeypatch.setitem(cli_module.SPECS, "freesound", patched)

    def test_download_from_manifest_end_to_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        fake = FakeProvider()
        self._patch_spec(monkeypatch, fake)

        outdir = tmp_path / "out"
        manifest = outdir / "manifest.jsonl"
        append_record(
            manifest,
            {
                "provider": "freesound",
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
        # Prevent the repo-root .env from being loaded during the test.
        monkeypatch.setattr("soundfetch.cli._load_dotenv", lambda: None)

        result = CliRunner().invoke(main, ["freesound", "status"])

        assert result.exit_code == 0
        assert "api_key: missing" in result.output

    def test_download_requires_query_or_manifest(self):
        result = CliRunner().invoke(main, ["freesound", "download"])
        assert result.exit_code != 0
        assert "QUERY or --manifest" in result.output


# ---------------------------------------------------------------------------
# Video CLI
# ---------------------------------------------------------------------------


class TestVideoCli:
    def _patch_spec(self, monkeypatch, fake: FakeProvider):
        original = SPECS["video"]
        patched = replace(original, build=lambda **kw: fake)
        monkeypatch.setitem(cli_module.SPECS, "video", patched)

    def test_search_writes_manifest(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        page = SearchPage(results=[make_ref("abc", name="Rain")], total=1, has_more=False)
        fake = FakeProvider(pages=[page])
        self._patch_spec(monkeypatch, fake)

        outdir = tmp_path / "out"
        result = CliRunner().invoke(main, ["video", "search", "rain ambience", "-o", str(outdir)])

        assert result.exit_code == 0, result.output
        assert (outdir / "manifest.jsonl").exists()

    def test_download_from_manifest_end_to_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        fake = FakeProvider()
        self._patch_spec(monkeypatch, fake)

        outdir = tmp_path / "out"
        manifest = outdir / "manifest.jsonl"
        append_record(
            manifest,
            {
                "provider": "video",
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
