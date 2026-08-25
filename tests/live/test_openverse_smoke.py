"""Deliberate real-network smoke checks for the anonymous Openverse API."""

from pathlib import Path

import pytest

from soundfetch.core.model import SearchParams
from soundfetch.providers.openverse.provider import OpenverseProvider


@pytest.mark.live
def test_openverse_search_and_small_download(tmp_path: Path):
    provider = OpenverseProvider()
    page = provider.search(
        SearchParams(
            query="bird",
            page_size=20,
            max_results=20,
        )
    )

    assert page.results
    downloadable = [item for item in page.results if item.download_url]
    ref = min(
        downloadable,
        key=lambda item: item.metadata.get("filesize") or float("inf"),
        default=None,
    )
    assert ref is not None
    assert ref.provider == "openverse"
    assert ref.metadata["openverse_id"] == ref.provider_id
    assert ref.metadata.get("attribution")

    result = provider.download(ref, tmp_path)
    assert result.status == "downloaded"
    assert result.bytes > 0
    assert result.local_path.is_file()
