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

    def test_search_rejects_excessive_max_results(self, tmp_path: Path):
        refs = [make_ref(str(i)) for i in range(300)]
        page = type("SearchPage", (), {"results": refs, "total": 300, "has_more": False})()
        provider = FakeProvider(pages=[page])

        result = tool_search_sounds("test", max_results=300, provider="fake", providers={"fake": provider})

        assert result["ok"] is False
        assert "between 1 and 50" in result["error"]

    def test_search_returns_compact_compliance_fields(self):
        ref = make_ref(
            "1",
            metadata={
                "license": "CC0",
                "duration": 1.5,
                "tags": ["rain"],
                "gen_ai_preference": "allow",
                "description": "intentionally omitted from agent response",
            },
        )
        page = type("SearchPage", (), {"results": [ref], "total": 1, "has_more": False})()
        provider = FakeProvider(pages=[page])

        result = tool_search_sounds(
            "rain", provider="fake", gen_ai="allow", providers={"fake": provider}
        )

        assert result["results"] == [{
            "provider": "fake",
            "provider_id": "1",
            "name": "sound",
            "url": "https://example.test/1",
            "file_format": "wav",
            "license": "CC0",
            "duration": 1.5,
            "tags": ["rain"],
            "gen_ai_preference": "allow",
        }]
        assert provider.search_params[0].filters["gen_ai"] == "allow"

    @pytest.mark.parametrize("query,max_results", [("   ", 1), ("rain", 0), ("rain", 51)])
    def test_search_validates_agent_limits(self, query: str, max_results: int):
        result = tool_search_sounds(query, max_results=max_results, providers={})
        assert result["ok"] is False

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

    def test_partial_failure_is_not_reported_as_ok(self, tmp_path: Path):
        from ..fakes import failing_download

        manifest = tmp_path / "manifest.jsonl"
        _write_manifest(manifest, [
            {"provider": "fake", "provider_id": "1", "name": "a", "status": "listed"},
        ])
        result = tool_download_manifest(
            str(manifest),
            dest_dir=str(tmp_path / "out"),
            providers={"fake": FakeProvider(download_fn=failing_download())},
        )

        assert result["ok"] is False
        assert result["status"] == "partial"
        assert result["failed"] == 1
        assert result["errors"] == ["boom on 1"]

    @pytest.mark.parametrize("workers,rate", [(0, None), (1, 0), (1, -1)])
    def test_download_validates_controls(self, tmp_path: Path, workers: int, rate: float | None):
        manifest = tmp_path / "manifest.jsonl"
        manifest.touch()
        result = tool_download_manifest(str(manifest), workers=workers, rate=rate)
        assert result["ok"] is False


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
