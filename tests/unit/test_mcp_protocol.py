"""Optional end-to-end MCP protocol checks against the installed SDK."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path
import sys

import pytest


def test_stdio_handshake_tools_and_structured_result():
    pytest.importorskip("mcp")
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def exercise() -> None:
        executable = Path(sys.executable).with_name("soundfetch")
        command = str(executable) if executable.exists() else "soundfetch"
        params = StdioServerParameters(command=command, args=["mcp"])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=10)) as session:
                initialized = await session.initialize()
                tools = await session.list_tools()
                result = await session.call_tool("list_sources", {})

        assert initialized.serverInfo.name == "soundfetch"
        assert {tool.name for tool in tools.tools} == {
            "search_sounds",
            "download_manifest",
            "check_provider_status",
            "list_sources",
        }
        assert result.isError is False
        assert result.structuredContent is not None
        # Tools are typed `-> str` and return json.dumps(...); the SDK wraps an
        # unstructured string return as {"result": "<json>"}, so callers must
        # decode twice to reach the actual payload.
        payload = json.loads(result.structuredContent["result"])
        assert payload["ok"] is True

    asyncio.run(exercise())
