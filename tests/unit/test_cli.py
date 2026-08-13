"""Tests for the spec-driven CLI (soundfetch.cli).

Monkeypatch seams use ``monkeypatch.setitem(cli_module.SPECS, ...)``
so command callbacks resolve the patched spec at call time (not import time).
"""

from __future__ import annotations

import json
import subprocess
import sys
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


def test_package_module_entry_point_runs_cli(tmp_path: Path):
    """The installed package must support PluginForge's exact invocation form."""
    result = subprocess.run(
        [sys.executable, "-m", "soundfetch", "sources", "--json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert {row["name"] for row in payload["sources"]} >= {"archive", "freesound"}


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

    def test_search_reports_metadata_progress_on_stderr(self, tmp_path, monkeypatch):
        class ProgressProvider(FakeProvider):
            def search(self, params, *, progress=None):
                if progress is not None:
                    progress(1, 2)
                    progress(2, 2)
                return super().search(params, progress=progress)

        fake = ProgressProvider(
            pages=[
                SearchPage(
                    results=[replace(make_ref("1"), provider="archive")],
                    total=1,
                    has_more=False,
                )
            ]
        )
        self._patch_spec(monkeypatch, fake)

        result = CliRunner().invoke(
            main, ["archive", "search", "rain", "-o", str(tmp_path / "out")]
        )

        assert result.exit_code == 0, result.output
        assert "archive metadata: 1/2" in result.stderr
        assert "archive metadata: 2/2" in result.stderr

    def test_json_search_keeps_stdout_parseable_and_progress_on_stderr(
        self, tmp_path, monkeypatch
    ):
        import json

        class ProgressProvider(FakeProvider):
            def search(self, params, *, progress=None):
                if progress is not None:
                    progress(1, 1)
                return super().search(params, progress=progress)

        fake = ProgressProvider(
            pages=[SearchPage(results=[make_ref("1")], total=1, has_more=False)]
        )
        self._patch_spec(monkeypatch, fake)

        result = CliRunner().invoke(
            main,
            ["archive", "search", "rain", "--json", "-o", str(tmp_path / "out")],
        )

        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["ok"] is True
        assert "archive metadata: 1/1" in result.stderr

    def test_query_download_reports_metadata_progress_on_stderr(
        self, tmp_path, monkeypatch
    ):
        class ProgressProvider(FakeProvider):
            def search(self, params, *, progress=None):
                if progress is not None:
                    progress(1, 1)
                return super().search(params, progress=progress)

        fake = ProgressProvider(
            pages=[
                SearchPage(
                    results=[replace(make_ref("1"), provider="archive")],
                    total=1,
                    has_more=False,
                )
            ]
        )
        self._patch_spec(monkeypatch, fake)

        result = CliRunner().invoke(
            main,
            ["archive", "download", "rain", "-o", str(tmp_path / "out")],
        )

        assert result.exit_code == 0, result.output
        assert "archive metadata: 1/1" in result.stderr
        assert fake.download_calls == ["1"]

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

    def test_json_download_filters_manifest_by_provider_id(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        fake = FakeProvider()
        self._patch_spec(monkeypatch, fake)

        outdir = tmp_path / "out"
        manifest = outdir / "manifest.jsonl"
        for provider_id in ("1", "2", "3"):
            append_record(
                manifest,
                {
                    "provider": "archive",
                    "provider_id": provider_id,
                    "name": f"rain-{provider_id}",
                    "file_format": "wav",
                    "status": "listed",
                },
            )

        result = CliRunner().invoke(
            main,
            [
                "archive", "download", "--manifest", str(manifest),
                "--provider-id", "2", "--json", "-o", str(outdir),
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["ok"] is True
        assert payload["command"] == "download"
        assert payload["provider"] == "archive"
        assert payload["manifest"] == str(manifest)
        assert [item["provider_id"] for item in payload["items"]] == ["2"]
        assert payload["items"][0]["local_path"].endswith("rain-2.wav")
        assert fake.download_calls == ["2"]

    def test_json_download_accepts_repeated_provider_ids_in_manifest_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        fake = FakeProvider()
        self._patch_spec(monkeypatch, fake)
        outdir = tmp_path / "out"
        manifest = outdir / "manifest.jsonl"
        for provider_id in ("1", "2", "3"):
            append_record(
                manifest,
                {
                    "provider": "archive",
                    "provider_id": provider_id,
                    "name": f"rain-{provider_id}",
                    "file_format": "wav",
                    "status": "listed",
                },
            )

        result = CliRunner().invoke(
            main,
            [
                "archive", "download", "--manifest", str(manifest),
                "--provider-id", "3", "--provider-id", "1",
                "--json", "-o", str(outdir),
            ],
        )

        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert [item["provider_id"] for item in payload["items"]] == ["1", "3"]
        assert fake.download_calls == ["1", "3"]

    def test_json_download_reports_missing_provider_id_without_downloading(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        fake = FakeProvider()
        self._patch_spec(monkeypatch, fake)
        manifest = tmp_path / "manifest.jsonl"
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
                "archive", "download", "--manifest", str(manifest),
                "--provider-id", "missing", "--json", "-o", str(tmp_path / "out"),
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert payload["error"]["type"] == "ClickException"
        assert "missing" in payload["error"]["message"]
        assert fake.download_calls == []

    def test_provider_id_requires_manifest_in_json_mode(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        fake = FakeProvider()
        self._patch_spec(monkeypatch, fake)

        result = CliRunner().invoke(
            main,
            [
                "archive", "download", "rain", "--provider-id", "1",
                "--json", "-o", str(tmp_path / "out"),
            ],
        )

        assert result.exit_code != 0
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert "requires --manifest" in payload["error"]["message"]
        assert fake.download_calls == []

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
