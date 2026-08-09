"""Unit tests for soundfetch.adapters — framework tool builder wrappers.

Gated behind importorskip so they run only when the respective framework is
installed in the environment.
"""

from __future__ import annotations

import pytest


def test_langchain_tools():
    pytest.importorskip("langchain_core")
    from soundfetch.adapters import langchain_tools

    tools = langchain_tools()
    assert len(tools) == 4
    names = {t.name for t in tools}
    assert "search_sounds" in names
    assert "download_manifest" in names


def test_llamaindex_tools():
    pytest.importorskip("llama_index.core")
    from soundfetch.adapters import llamaindex_tools

    tools = llamaindex_tools()
    assert len(tools) == 4


def test_smolagents_tools():
    pytest.importorskip("smolagents")
    from soundfetch.adapters import smolagents_tools

    tools = smolagents_tools()
    assert len(tools) == 4
