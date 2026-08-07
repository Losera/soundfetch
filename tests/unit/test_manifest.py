from __future__ import annotations

from pathlib import Path

from soundfetch.core.manifest import append_record, iter_latest, latest_by_sound, read_records


def test_read_records_missing_file_returns_empty(tmp_path: Path):
    assert read_records(tmp_path / "nope.jsonl") == []


def test_append_and_read_round_trip(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    append_record(manifest, {"provider": "fake", "provider_id": "1", "status": "listed"})
    append_record(manifest, {"provider": "fake", "provider_id": "2", "status": "listed"})
    records = read_records(manifest)
    assert [r["provider_id"] for r in records] == ["1", "2"]


def test_append_record_creates_parent_dir(tmp_path: Path):
    manifest = tmp_path / "nested" / "manifest.jsonl"
    append_record(manifest, {"provider": "fake", "provider_id": "1"})
    assert manifest.exists()


def test_read_records_tolerates_torn_last_line(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    append_record(manifest, {"provider": "fake", "provider_id": "1", "status": "listed"})
    with open(manifest, "a", encoding="utf-8") as fh:
        fh.write('{"provider": "fake", "provider_id": "2", "stat')  # torn, no trailing newline
    records = read_records(manifest)
    assert len(records) == 1
    assert records[0]["provider_id"] == "1"


def test_read_records_skips_blank_lines(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text('{"provider": "fake", "provider_id": "1"}\n\n\n', encoding="utf-8")
    assert len(read_records(manifest)) == 1


def test_latest_by_sound_is_last_wins(tmp_path: Path):
    records = [
        {"provider": "fake", "provider_id": "1", "status": "listed"},
        {"provider": "fake", "provider_id": "1", "status": "downloaded"},
        {"provider": "fake", "provider_id": "2", "status": "listed"},
    ]
    latest = latest_by_sound(records)
    assert latest[("fake", "1")]["status"] == "downloaded"
    assert latest[("fake", "2")]["status"] == "listed"
    assert len(latest) == 2


def test_iter_latest_reads_from_manifest(tmp_path: Path):
    manifest = tmp_path / "manifest.jsonl"
    append_record(manifest, {"provider": "fake", "provider_id": "1", "status": "listed"})
    append_record(manifest, {"provider": "fake", "provider_id": "1", "status": "downloaded"})
    results = list(iter_latest(manifest))
    assert len(results) == 1
    assert results[0]["status"] == "downloaded"


def test_provider_id_key_is_stringified(tmp_path: Path):
    # provider_id may round-trip as an int through JSON; dedup key must match strings.
    records = [
        {"provider": "fake", "provider_id": 1, "status": "listed"},
        {"provider": "fake", "provider_id": "1", "status": "downloaded"},
    ]
    latest = latest_by_sound(records)
    assert len(latest) == 1
    assert latest[("fake", "1")]["status"] == "downloaded"
