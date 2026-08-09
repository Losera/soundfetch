"""LangChain tool adapter for soundfetch."""

from __future__ import annotations


def build_tools() -> list:
    """Build LangChain StructuredTool objects for soundfetch.

    Requires ``pip install "soundfetch[langchain]"``.
    """
    try:
        from langchain_core.tools import StructuredTool
    except ImportError:
        raise ImportError(
            "LangChain adapter requires langchain-core. "
            'Install with: pip install "soundfetch[langchain]"'
        ) from None

    from ..mcp import (
        tool_search_sounds,
        tool_download_manifest,
        tool_check_provider_status,
        tool_list_sources,
    )

    return [
        StructuredTool.from_function(
            func=tool_search_sounds,
            name="soundfetch_search_sounds",
            description="Search a sound provider (freesound, archive, video) and return results. Supports license filtering and max results.",
        ),
        StructuredTool.from_function(
            func=tool_download_manifest,
            name="soundfetch_download_manifest",
            description="Download sounds from an existing manifest.jsonl file. Supports resume and overwrite.",
        ),
        StructuredTool.from_function(
            func=tool_check_provider_status,
            name="soundfetch_check_provider_status",
            description="Check the configuration status of a sound provider (API keys, auth tokens, packages).",
        ),
        StructuredTool.from_function(
            func=tool_list_sources,
            name="soundfetch_list_sources",
            description="List all registered sound source providers.",
        ),
    ]
