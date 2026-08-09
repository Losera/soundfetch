"""Smolagents tool adapter for soundfetch."""

from __future__ import annotations


def build_tools() -> list:
    """Build Smolagents Tool objects for soundfetch.

    Requires ``pip install "soundfetch[smolagents]"``.
    """
    try:
        from smolagents.tools import Tool
    except ImportError:
        raise ImportError(
            "Smolagents adapter requires the smolagents package. "
            'Install with: pip install "soundfetch[smolagents]"'
        ) from None

    from ..mcp import (
        tool_search_sounds,
        tool_download_manifest,
        tool_check_provider_status,
        tool_list_sources,
    )

    tools = []
    for fn in (
        tool_search_sounds,
        tool_download_manifest,
        tool_check_provider_status,
        tool_list_sources,
    ):
        tool = Tool.from_function(
            fn,
            name=f"soundfetch_{fn.__name__.removeprefix('tool_')}",
            description=fn.__doc__ or "",
        )
        tools.append(tool)
    return tools
