from __future__ import annotations

import argparse
import json
import sys
from types import SimpleNamespace

import pytest

from scripts import benchmark_api


class _Response:
    def __init__(self, size: str) -> None:
        self.headers = {"Content-Length": size}

    def raise_for_status(self) -> None:
        return None


class _Session:
    def __init__(self, sizes: dict[str, str]) -> None:
        self.sizes = sizes

    def head(self, url: str, **_kwargs) -> _Response:
        return _Response(self.sizes[url])


def test_bounded_refs_enforces_per_file_and_total_caps(monkeypatch) -> None:
    refs = [
        SimpleNamespace(download_url="https://example.test/one"),
        SimpleNamespace(download_url="https://example.test/oversized"),
        SimpleNamespace(download_url="https://example.test/two"),
        SimpleNamespace(download_url=None),
    ]
    sizes = {
        "https://example.test/one": "400",
        "https://example.test/oversized": "1200",
        "https://example.test/two": "350",
    }
    monkeypatch.setattr(benchmark_api.requests, "Session", lambda: _Session(sizes))

    selected, total = benchmark_api._bounded_refs(
        refs,
        max_file_bytes=1000,
        remaining_bytes=700,
    )

    assert selected == [refs[0]]
    assert total == 400


@pytest.mark.parametrize("value", ["", "0", "1,0", "one", "1,two"])
def test_parse_worker_counts_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        benchmark_api._parse_worker_counts(value)


def test_parse_worker_counts_preserves_requested_configurations() -> None:
    assert benchmark_api._parse_worker_counts("1,4") == [1, 4]


def test_run_metadata_records_reproducibility_fields(monkeypatch) -> None:
    responses = iter([SimpleNamespace(stdout="abc123\n"), SimpleNamespace(stdout="")])
    monkeypatch.setattr(benchmark_api.subprocess, "run", lambda *_args, **_kwargs: next(responses))
    monkeypatch.setattr(benchmark_api.platform, "platform", lambda: "test-platform")
    args = argparse.Namespace(
        query="rain",
        limit=10,
        trials=3,
        max_file_mb=1,
        max_total_mb=100,
    )

    metadata = benchmark_api._run_metadata(args, [1, 4])

    assert metadata["commit"] == "abc123"
    assert metadata["dirty"] is False
    assert metadata["platform"] == "test-platform"
    assert metadata["query"] == "rain"
    assert metadata["limit"] == 10
    assert metadata["trials"] == 3
    assert metadata["workers"] == [1, 4]
    assert metadata["max_file_mb"] == 1
    assert metadata["max_total_mb"] == 100
    assert metadata["recorded_at"]


def test_main_retains_run_evidence_when_no_configuration_completes(
    monkeypatch,
    tmp_path,
) -> None:
    output_dir = tmp_path / "failed-run"
    monkeypatch.setattr(benchmark_api, "DEFAULT_SOURCES", ())
    monkeypatch.setattr(benchmark_api, "_plot_dependencies", lambda: (object(), object()))
    monkeypatch.setattr(
        sys,
        "argv",
        ["benchmark_api.py", "--outdir", str(output_dir)],
    )

    assert benchmark_api.main() == 1
    run = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    failures = json.loads((output_dir / "failures.json").read_text(encoding="utf-8"))
    assert run["completed_configurations"] == 0
    assert run["failed_configurations"] == 0
    assert run["sources"] == []
    assert failures == []
