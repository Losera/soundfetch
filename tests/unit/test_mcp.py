"""Unit tests for soundfetch.mcp — MCP tool functions (SDK-independent)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ..fakes import FakeProvider, make_ref

# Import the tool functions directly — they are plain callables with no MCP dep.
from soundfetch.mcp import (
    tool_check_provider_status,
    tool_download_manifest,
    tool_list_sources,
    tool_report_manifest,
    tool_search_sounds,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_specs():
    """Minimal specs dict for tool_check_provider_status / tool_list_sources."""
    from unittest.mock import MagicMock

    fake_spec = MagicMock()
    fake_spec.help = "test provider"
    fake_spec.status_hint = None
    fake_spec.status_labels = {}
    fake_spec.status_missing_hint = ""
    return {"fake": fake_spec}


def _write_manifest(path: Path, records: list[dict[str, Any]]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


@pytest.fixture(autouse=True)
def _mcp_workspace_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Confine the MCP path-confinement root to this test's tmp_path, so
    tests that write manifests/output under tmp_path (the normal pattern in
    this file) keep working without each one setting the env var by hand.
    Tests exercising the confinement boundary itself override this."""
    monkeypatch.setenv("SOUNDFETCH_MCP_ROOT", str(tmp_path))


# ---------------------------------------------------------------------------
# tool_search_sounds
# ---------------------------------------------------------------------------


class TestToolSearchSounds:
    def test_search_returns_results(self, tmp_path: Path):
        ref = make_ref("1", name="rain", url="https://example.test/1")
        page = type("SearchPage", (), {"results": [ref], "total": 1, "has_more": False})()
        provider = FakeProvider(pages=[page])
        providers = {"fake": provider}

        result = tool_search_sounds("rain", provider="fake", providers=providers)

        assert result["ok"] is True
        assert result["count"] == 1
        assert result["results"][0]["provider_id"] == "1"
        assert result["results"][0]["name"] == "rain"

    def test_search_caps_max_results(self, tmp_path: Path):
        refs = [make_ref(str(i)) for i in range(300)]
        page = type("SearchPage", (), {"results": refs, "total": 300, "has_more": False})()
        provider = FakeProvider(pages=[page])

        result = tool_search_sounds("test", max_results=300, provider="fake", providers={"fake": provider})

        assert result["count"] == 200  # capped at 200

    def test_search_with_manifest_saves(self, tmp_path: Path):
        ref = make_ref("1")
        page = type("SearchPage", (), {"results": [ref], "total": 1, "has_more": False})()
        provider = FakeProvider(pages=[page])
        manifest_path = str(tmp_path / "manifest.jsonl")

        result = tool_search_sounds(
            "rain", provider="fake", manifest=manifest_path, providers={"fake": provider}
        )

        assert result["ok"] is True
        assert "manifest" in result
        assert Path(manifest_path).exists()

    def test_search_error_returns_ok_false(self):
        result = tool_search_sounds("rain", provider="nonexistent", providers={})

        assert result["ok"] is False
        assert "error" in result

    def test_manifest_path_escaping_workspace_is_rejected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """A model-chosen `manifest` path (plausibly reachable via a
        prompt-injected instruction) must not be able to write outside the
        soundfetch workspace, e.g. `~/.bashrc` (the H-5 finding)."""
        monkeypatch.setenv("SOUNDFETCH_MCP_ROOT", str(tmp_path / "workspace"))
        ref = make_ref("1")
        page = type("SearchPage", (), {"results": [ref], "total": 1, "has_more": False})()
        provider = FakeProvider(pages=[page])
        outside = tmp_path / "outside" / "pwned.jsonl"

        result = tool_search_sounds(
            "rain", provider="fake", manifest=str(outside), providers={"fake": provider}
        )

        assert result["ok"] is False
        assert "workspace" in result["error"]
        assert not outside.exists()

    def test_long_description_field_is_truncated(self, tmp_path: Path):
        """Uploader-supplied free text (Freesound description/tags,
        Archive.org title/description) reaches the model's context with no
        other sanitization; length is capped as a blast-radius bound (H-4)."""
        huge = "x" * 10_000
        ref = make_ref("1", name="rain", metadata={"description": huge})
        page = type("SearchPage", (), {"results": [ref], "total": 1, "has_more": False})()
        provider = FakeProvider(pages=[page])

        result = tool_search_sounds(
            "rain",
            provider="fake",
            providers={"fake": provider},
            include_metadata=True,
        )

        description = result["results"][0]["metadata"]["description"]
        assert len(description) < len(huge)
        assert description.endswith("[truncated]")

    def test_search_defaults_to_summary_and_forwards_filters(self, tmp_path: Path):
        ref = make_ref(
            "1",
            metadata={
                "license": "cc0",
                "username": "recorder",
                "duration_ms": 1500,
                "filesize": 42,
                "attribution": "Bird by recorder, CC0",
                "description": "omitted by default",
            },
        )
        page = type(
            "SearchPage", (), {"results": [ref], "total": 1, "has_more": False}
        )()
        provider = FakeProvider(pages=[page])

        result = tool_search_sounds(
            "bird",
            provider="fake",
            providers={"fake": provider},
            duration="short",
            tag="nature",
            category="sound_effect",
            source="freesound",
            extension="mp3",
            length="shortest",
            gen_ai="deny",
            sort="relevance",
        )

        item = result["results"][0]
        assert item["license"] == "cc0"
        assert item["creator"] == "recorder"
        assert item["duration_seconds"] == 1.5
        assert item["filesize"] == 42
        assert "metadata" not in item
        assert provider.search_params[0].filters == {
            "duration": "short",
            "tag": "nature",
            "category": "sound_effect",
            "source": "freesound",
            "extension": "mp3",
            "length": "shortest",
            "gen_ai": "deny",
        }
        assert provider.search_params[0].sort == "relevance"


# ---------------------------------------------------------------------------
# tool_download_manifest
# ---------------------------------------------------------------------------


class TestToolDownloadManifest:
    def test_download_from_manifest(self, tmp_path: Path):
        manifest = tmp_path / "manifest.jsonl"
        _write_manifest(manifest, [
            {"provider": "fake", "provider_id": "1", "name": "a", "status": "listed"},
            {"provider": "fake", "provider_id": "2", "name": "b", "status": "listed"},
        ])

        provider = FakeProvider()
        providers = {"fake": provider}

        result = tool_download_manifest(
            str(manifest), dest_dir=str(tmp_path / "out"), providers=providers
        )

        assert result["ok"] is True
        assert result["downloaded"] == 2
        assert result["skipped"] == 0
        assert provider.download_calls == ["1", "2"]

    def test_empty_manifest_returns_no_pending(self, tmp_path: Path):
        manifest = tmp_path / "empty.jsonl"
        manifest.touch()

        result = tool_download_manifest(str(manifest), dest_dir=str(tmp_path / "out"))

        assert result["ok"] is True
        assert result["downloaded"] == 0
        assert result["skipped"] == 0
        assert "no pending" in result["message"]

    def test_resume_skips_already_downloaded(self, tmp_path: Path):
        manifest = tmp_path / "manifest.jsonl"
        _write_manifest(manifest, [
            {"provider": "fake", "provider_id": "1", "name": "a", "status": "downloaded",
             "local_file": "a.wav"},
        ])
        # Create the file on disk so resume check passes
        (tmp_path / "out").mkdir(exist_ok=True)
        (tmp_path / "out" / "a.wav").write_bytes(b"data")

        result = tool_download_manifest(
            str(manifest), dest_dir=str(tmp_path / "out"),
            providers={"fake": FakeProvider()},
        )

        assert result["ok"] is True
        assert result["skipped"] == 1
        assert result["downloaded"] == 0

    def test_provider_ids_select_in_manifest_order(self, tmp_path: Path):
        manifest = tmp_path / "manifest.jsonl"
        _write_manifest(
            manifest,
            [
                {"provider": "fake", "provider_id": "1", "name": "a", "status": "listed"},
                {"provider": "fake", "provider_id": "2", "name": "b", "status": "listed"},
                {"provider": "fake", "provider_id": "3", "name": "c", "status": "listed"},
            ],
        )
        provider = FakeProvider()

        result = tool_download_manifest(
            str(manifest),
            dest_dir=str(tmp_path / "out"),
            provider_ids=["3", "1"],
            providers={"fake": provider},
        )

        assert result["ok"] is True
        assert provider.download_calls == ["1", "3"]

    def test_missing_provider_id_does_not_download(self, tmp_path: Path):
        manifest = tmp_path / "manifest.jsonl"
        _write_manifest(
            manifest,
            [{"provider": "fake", "provider_id": "1", "status": "listed"}],
        )
        provider = FakeProvider()

        result = tool_download_manifest(
            str(manifest),
            provider_ids=["missing"],
            providers={"fake": provider},
        )

        assert result["ok"] is False
        assert "missing" in result["error"]
        assert provider.download_calls == []


class TestToolReportManifest:
    def test_reports_manifest_without_writing(self, tmp_path: Path):
        manifest = tmp_path / "manifest.jsonl"
        _write_manifest(
            manifest,
            [{"provider": "fake", "provider_id": "1", "status": "listed"}],
        )
        original = manifest.read_bytes()

        result = tool_report_manifest(str(manifest))

        assert result["ok"] is True
        assert result["records"]["effective"] == 1
        assert manifest.read_bytes() == original

    def test_rejects_manifest_outside_workspace(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("SOUNDFETCH_MCP_ROOT", str(tmp_path / "workspace"))

        result = tool_report_manifest(str(tmp_path / "outside.jsonl"))

        assert result["ok"] is False
        assert "workspace" in result["error"]


# ---------------------------------------------------------------------------
# tool_list_sources
# ---------------------------------------------------------------------------


class TestToolListSources:
    def test_list_sources_returns_ok(self):
        result = tool_list_sources()
        assert result["ok"] is True
        assert "sources" in result
        names = [s["name"] for s in result["sources"]]
        # At minimum the core providers should be listed
        assert isinstance(names, list)


# ---------------------------------------------------------------------------
# tool_check_provider_status
# ---------------------------------------------------------------------------


class TestToolCheckProviderStatus:
    def test_unknown_provider(self):
        result = tool_check_provider_status("nonexistent")
        assert result["ok"] is False
        assert "unknown provider" in result["error"]

    def test_fake_provider_with_status(self):
        from unittest.mock import MagicMock

        fake_spec = MagicMock()
        fake_spec.help = "test"
        fake_spec.status_hint = None
        fake_spec.status_labels = {"api_key": "API Key", "token": "Token"}
        fake_spec.status_missing_hint = "set it"
        fake_spec.build = lambda: FakeProvider()
        specs = {"fake": fake_spec}

        result = tool_check_provider_status("fake", specs=specs)

        assert result["ok"] is True
        assert result["provider"] == "fake"
