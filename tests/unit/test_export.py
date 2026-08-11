"""Unit tests for soundfetch.export — export_attribution, _select_downloaded,
and to_webdataset.

to_webdataset is gated behind importorskip so it runs only when the
webdataset/soundfile optional deps are installed (see the `export` CI job).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from soundfetch.core.manifest import append_record, iter_latest
from soundfetch.export import _select_downloaded, export_attribution


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_manifest(path: Path, records: list[dict]) -> None:
    for rec in records:
        append_record(path, rec)


def _make_record(
    provider_id: str,
    status: str = "downloaded",
    local_file: str | None = None,
    name: str = "sound",
    **extra,
) -> dict:
    rec = {
        "provider": "test",
        "provider_id": provider_id,
        "name": name,
        "status": status,
        "local_file": local_file,
        "url": f"https://example.test/{provider_id}",
        "metadata": {
            "license": "CC0 1.0",
            "username": "tester",
            "gen_ai_preference": "yes",
        },
    }
    rec.update(extra)
    return rec


# ---------------------------------------------------------------------------
# _select_downloaded
# ---------------------------------------------------------------------------


class TestSelectDownloaded:
    def test_filters_downloaded_records(self, tmp_path: Path):
        manifest = tmp_path / "manifest.jsonl"
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (out_dir / "1.wav").write_bytes(b"data")

        _write_manifest(manifest, [
            _make_record("1", status="downloaded", local_file="1.wav"),
            _make_record("2", status="listed"),
            _make_record("3", status="error"),
        ])

        results = _select_downloaded(manifest, dest_dir=out_dir)
        assert len(results) == 1
        assert results[0]["provider_id"] == "1"
        assert results[0]["local_path"] == (out_dir / "1.wav").resolve()

    def test_skips_empty_local_file(self, tmp_path: Path):
        manifest = tmp_path / "manifest.jsonl"
        _write_manifest(manifest, [
            _make_record("1", status="downloaded", local_file=""),
            _make_record("2", status="downloaded", local_file=None),
        ])

        results = _select_downloaded(manifest, dest_dir=tmp_path)
        assert len(results) == 0

    def test_adds_author_from_metadata(self, tmp_path: Path):
        manifest = tmp_path / "manifest.jsonl"
        (tmp_path / "1.wav").write_bytes(b"data")
        _write_manifest(manifest, [
            _make_record("1", local_file="1.wav", name="rain"),
        ])

        results = _select_downloaded(manifest, dest_dir=tmp_path)
        assert results[0]["author"] == "tester"
        assert results[0]["license_text"] == "CC0 1.0"

    def test_defaults_for_missing_metadata(self, tmp_path: Path):
        manifest = tmp_path / "manifest.jsonl"
        (tmp_path / "1.wav").write_bytes(b"data")
        rec = _make_record("1", local_file="1.wav")
        rec["metadata"] = {}
        _write_manifest(manifest, [rec])

        results = _select_downloaded(manifest, dest_dir=tmp_path)
        assert results[0]["author"] == ""
        assert results[0]["license_text"] == ""


# ---------------------------------------------------------------------------
# export_attribution
# ---------------------------------------------------------------------------


class TestExportAttribution:
    def test_creates_attribution_markdown(self, tmp_path: Path):
        manifest = tmp_path / "manifest.jsonl"
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        (out_dir / "1.wav").write_bytes(b"data")

        _write_manifest(manifest, [
            _make_record("1", local_file="1.wav", name="rain"),
            _make_record("2", local_file="2.wav", name="thunder"),
        ])
        (out_dir / "2.wav").write_bytes(b"data")

        out_file = tmp_path / "ATTRIBUTION.md"
        result = export_attribution(manifest, dest_dir=out_dir, out_path=out_file)

        assert result == out_file
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "Sound Attribution" in content
        assert "rain" in content
        assert "thunder" in content
        assert "CC0 1.0" in content

    def test_empty_manifest_creates_header_only(self, tmp_path: Path):
        manifest = tmp_path / "empty.jsonl"
        manifest.write_text("", encoding="utf-8")

        out_file = tmp_path / "ATTRIBUTION.md"
        export_attribution(manifest, dest_dir=tmp_path, out_path=out_file)

        content = out_file.read_text(encoding="utf-8")
        assert "Sound Attribution" in content

    def test_gen_ai_in_attribution(self, tmp_path: Path):
        manifest = tmp_path / "manifest.jsonl"
        (tmp_path / "1.wav").write_bytes(b"data")
        _write_manifest(manifest, [
            _make_record("1", local_file="1.wav", name="ai-sound"),
        ])

        out_file = tmp_path / "ATTRIBUTION.md"
        export_attribution(manifest, dest_dir=tmp_path, out_path=out_file)

        content = out_file.read_text(encoding="utf-8")
        assert "Gen-AI" in content


# ---------------------------------------------------------------------------
# to_webdataset
# ---------------------------------------------------------------------------


class TestToWebdataset:
    def test_writes_readable_shard(self, tmp_path: Path):
        pytest.importorskip("webdataset")
        soundfile = pytest.importorskip("soundfile")
        import numpy as np
        import webdataset as wds

        from soundfetch.export import to_webdataset

        manifest = tmp_path / "manifest.jsonl"
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        wav_path = out_dir / "1.wav"
        soundfile.write(wav_path, np.zeros(1600, dtype="float32"), 16000)

        _write_manifest(manifest, [
            _make_record("1", local_file="1.wav", name="rain"),
        ])

        shard_dir = tmp_path / "shards"
        shards = to_webdataset(manifest, dest_dir=out_dir, out_dir=str(shard_dir))

        assert len(shards) == 1
        assert shards[0].exists()

        samples = list(wds.WebDataset(str(shards[0]), shardshuffle=False).decode())
        assert len(samples) == 1
        sample = samples[0]
        assert sample["__key__"] == "test_1"
        assert "wav" in sample
        meta = sample["json"]
        assert meta["sound_id"] == "1"
        assert meta["name"] == "rain"
        assert meta["license"] == "CC0 1.0"

    def test_raises_on_empty_manifest(self, tmp_path: Path):
        pytest.importorskip("webdataset")
        from soundfetch.export import to_webdataset

        manifest = tmp_path / "empty.jsonl"
        manifest.write_text("", encoding="utf-8")

        with pytest.raises(ValueError, match="no downloaded sounds"):
            to_webdataset(manifest, dest_dir=tmp_path, out_dir=str(tmp_path / "shards"))
