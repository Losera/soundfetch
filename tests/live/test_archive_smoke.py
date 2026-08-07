"""Live smoke test against the real Internet Archive API.

Skipped by default (pyproject.toml sets `addopts = -m "not live"`); run
explicitly with `pytest -m live`. No API key needed (Internet Archive has
no auth), but it still hits the real network so it stays out of the
default offline run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from soundfetch.core.model import SearchParams
from soundfetch.providers.archive.provider import ArchiveProvider

pytestmark = pytest.mark.live


def test_search_returns_a_result():
    provider = ArchiveProvider()
    page = provider.search(SearchParams(query="piano", page_size=1, extra={"page": 1}))
    assert page.total > 0
    assert len(page.results) == 1
    assert page.results[0].download_url


def test_download_one_file(tmp_path: Path):
    provider = ArchiveProvider()
    page = provider.search(SearchParams(query="piano", page_size=1, extra={"page": 1}))
    ref = page.results[0]

    result = provider.download(ref, tmp_path)

    assert result.status == "downloaded"
    assert result.bytes > 0
    assert result.local_path.exists()
    assert result.local_path.stat().st_size == result.bytes
