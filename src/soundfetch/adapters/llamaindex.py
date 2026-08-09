"""LlamaIndex tool adapter for soundfetch."""

from __future__ import annotations


def build_tools() -> list:
    """Build LlamaIndex FunctionTool objects for soundfetch.

    Requires ``pip install "soundfetch[llamaindex]"``.
    """
    try:
        from llama_index.core.tools import FunctionTool
    except ImportError:
        raise ImportError(
            "LlamaIndex adapter requires llama-index-core. "
            'Install with: pip install "soundfetch[llamaindex]"'
        ) from None

    from ..mcp import (
        tool_search_sounds,
        tool_download_manifest,
        tool_check_provider_status,
        tool_list_sources,
    )

    return [
        FunctionTool.from_defaults(
            fn=tool_search_sounds,
            name="soundfetch_search_sounds",
            description="Search a sound provider (freesound, archive, video) and return results. Supports license filtering and max results.",
        ),
        FunctionTool.from_defaults(
            fn=tool_download_manifest,
            name="soundfetch_download_manifest",
            description="Download sounds from an existing manifest.jsonl file. Supports resume and overwrite.",
        ),
        FunctionTool.from_defaults(
            fn=tool_check_provider_status,
            name="soundfetch_check_provider_status",
            description="Check the configuration status of a sound provider (API keys, auth tokens, packages).",
        ),
        FunctionTool.from_defaults(
            fn=tool_list_sources,
            name="soundfetch_list_sources",
            description="List all registered sound source providers.",
        ),
    ]
