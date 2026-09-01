from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from soundfetch.cli import main
from soundfetch.report import build_manifest_report


def _write_manifest(path: Path, records: list[object]) -> None:
    lines = [
        json.dumps(record) if not isinstance(record, str) else record
        for record in records
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_report_uses_last_record_and_surfaces_quality_gaps(tmp_path: Path):
    audio = tmp_path / "rain.mp3"
    audio.write_bytes(b"audio")
    manifest = tmp_path / "manifest.jsonl"
    _write_manifest(
        manifest,
        [
            {
                "provider": "openverse",
                "provider_id": "one",
                "status": "listed",
                "url": "https://example.test/one",
                "metadata": {"license": "cc0", "duration_ms": 1500},
            },
            {
                "provider": "openverse",
                "provider_id": "one",
                "status": "downloaded",
                "url": "https://example.test/one",
                "local_file": "rain.mp3",
                "bytes": 5,
                "checksum": "abc",
                "metadata": {"license": "cc0", "duration_ms": 1500},
            },
            {
                "provider": "archive",
                "provider_id": "two",
                "status": "error",
                "metadata": {"licenseurl": "https://creativecommons.org/publicdomain/zero/1.0/"},
            },
            "not-json",
            ["not", "an", "object"],
        ],
    )

    report = build_manifest_report(manifest)

    assert report["records"] == {
        "valid": 3,
        "invalid": 2,
        "effective": 2,
        "superseded": 1,
    }
    assert report["status_counts"] == {"downloaded": 1, "error": 1}
    assert report["provider_counts"] == {"archive": 1, "openverse": 1}
    assert report["license_counts"] == {
        "cc0": 1,
        "https://creativecommons.org/publicdomain/zero/1.0/": 1,
    }
    assert report["downloads"] == {
        "count": 1,
        "bytes": 5,
        "duration_seconds": 1.5,
        "duration_known": 1,
        "duration_unknown": 0,
        "missing_local_files": 0,
        "missing_checksums": 0,
    }
    assert report["provenance"] == {
        "missing_license": 0,
        "missing_source_url": 1,
    }


def test_report_counts_unsafe_or_missing_download_paths(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    _write_manifest(
        manifest,
        [
            {
                "provider": "freesound",
                "provider_id": "one",
                "status": "downloaded",
                "local_file": "../outside.wav",
                "bytes": "12",
                "metadata": {"duration": "2.25"},
            }
        ],
    )

    report = build_manifest_report(manifest)

    assert report["downloads"]["bytes"] == 12
    assert report["downloads"]["duration_seconds"] == 2.25
    assert report["downloads"]["missing_local_files"] == 1
    assert report["downloads"]["missing_checksums"] == 1
    assert report["license_counts"] == {"missing": 1}


def test_report_uses_explicit_destination_without_modifying_manifest(tmp_path: Path):
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    (dataset / "sound.wav").write_bytes(b"audio")
    manifest = tmp_path / "reviewed.jsonl"
    _write_manifest(
        manifest,
        [
            {
                "provider": "archive",
                "provider_id": "one",
                "status": "downloaded",
                "url": "https://example.test/one",
                "local_file": "sound.wav",
                "checksum": "abc",
                "metadata": {"license": "cc0"},
            }
        ],
    )
    original = manifest.read_bytes()

    report = build_manifest_report(manifest, dest_dir=dataset)

    assert report["downloads"]["missing_local_files"] == 0
    assert manifest.read_bytes() == original


def test_manifest_report_cli_supports_subcommand_json(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    _write_manifest(manifest, [])

    result = CliRunner().invoke(main, ["manifest", "report", str(manifest), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["command"] == "manifest-report"
    assert payload["records"]["effective"] == 0


def test_manifest_report_cli_supports_root_json(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    _write_manifest(manifest, [])

    result = CliRunner().invoke(main, ["--json", "manifest", "report", str(manifest)])

    assert result.exit_code == 0
    assert json.loads(result.output)["ok"] is True


def test_manifest_report_cli_human_output_is_compact(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    _write_manifest(manifest, [])

    result = CliRunner().invoke(main, ["manifest", "report", str(manifest)])

    assert result.exit_code == 0
    assert "records: effective=0 valid=0 superseded=0 invalid=0" in result.output
    assert "providers: none" in result.output
    assert "gaps:" in result.output


def test_manifest_report_cli_missing_file_is_structured_json(tmp_path: Path):
    missing = tmp_path / "missing.jsonl"

    result = CliRunner().invoke(
        main, ["--json", "manifest", "report", str(missing)]
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["error"]["type"] == "FileNotFoundError"
