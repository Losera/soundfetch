"""Live smoke test against the real Freesound API.

Skipped by default (pyproject.toml sets `addopts = -m "not live"`); run
explicitly with `pytest -m live`. Requires FREESOUND_API_KEY, either as a
real env var or in a `.env` file in the repo root.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from soundfetch.core.model import SearchParams
from soundfetch.providers.freesound.provider import FreesoundProvider

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("FREESOUND_API_KEY"), reason="requires FREESOUND_API_KEY"
    ),
]


def test_search_returns_a_result():
    provider = FreesoundProvider()
    page = provider.search(SearchParams(query="piano", page_size=1, extra={"page": 1}))
    assert page.total > 0
    assert len(page.results) == 1


def test_download_one_hq_preview(tmp_path: Path):
    provider = FreesoundProvider(mode="preview", preview_quality="hq", preview_format="mp3")
    page = provider.search(SearchParams(query="piano", page_size=1, extra={"page": 1}))
    ref = page.results[0]

    result = provider.download(ref, tmp_path)

    assert result.status == "downloaded"
    assert result.bytes > 0
    assert result.local_path.exists()
    assert result.local_path.stat().st_size == result.bytes
