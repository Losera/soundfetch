"""soundfetch MCP server — expose soundfetch as Model Context Protocol tools.

Run via ``soundfetch mcp`` (stdio transport). Four tools are registered:

- **search_sounds** — search a provider, return results (optionally save
  to a manifest file).
- **download_manifest** — download sounds from an existing manifest
  (two-phase workflow: search first, review, then download).
- **check_provider_status** — check whether a provider is configured.
- **list_sources** — list all registered providers.

Tool functions are plain callables with injectable deps so they can be
unit-tested without installing the ``mcp`` SDK. Only ``create_server()``
and ``run()`` import ``mcp``.

Examples
--------
Register in Claude Desktop ``claude_desktop_config.json``::

    {
      "mcpServers": {
        "soundfetch": {
          "command": "soundfetch",
          "args": ["mcp"]
        }
      }
    }

Then use the tools:
- ``search_sounds("piano", license="cc0", max_results=10)``
- ``download_manifest("/path/to/manifest.jsonl", "/path/to/out/")``
- ``list_sources()``
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

__all__ = [
    "tool_search_sounds",
    "tool_download_manifest",
    "tool_check_provider_status",
    "tool_list_sources",
    "create_server",
    "run",
]


# ---------------------------------------------------------------------------
# Plain tool functions — no mcp import, fully testable with injectable deps
# ---------------------------------------------------------------------------


def tool_search_sounds(
    query: str,
    *,
    provider: str = "freesound",
    license: str | None = None,
    max_results: int = 50,
    manifest: str | None = None,
    providers: dict | None = None,
) -> dict[str, Any]:
    """Search a sound provider and return results as JSON-serializable dicts.

    Args:
        query: Search query string (e.g. "piano", "rain storm").
        provider: Provider name (e.g. "freesound", "archive", "video").
        license: Optional license filter (e.g. "cc0", "cc-by").
        max_results: Maximum number of results (default 50, max 200).
        manifest: Optional path to save results to a manifest file.
        providers: Injectable provider instances (for testing).

    Returns:
        ``{"ok": True, "count": int, "results": [...]}``
        or with ``"manifest": str`` if *manifest* was given.
        ``{"ok": False, "error": "message"}`` on failure.
    """
    from . import api

    try:
        refs = api.search(
            query,
            provider=provider,
            providers=providers,
            license=license,
            max_results=min(max_results, 200),
        )
        result: dict[str, Any] = {
            "ok": True,
            "count": len(refs),
            "results": [asdict(r) for r in refs],
        }
        if manifest:
            api.save_search(refs, manifest)
            result["manifest"] = str(manifest)
        return result
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def tool_download_manifest(
    manifest: str,
    dest_dir: str = "out",
    *,
    resume: bool = True,
    overwrite: bool = False,
    fail_fast: bool = False,
    providers: dict | None = None,
) -> dict[str, Any]:
    """Download sounds from an existing manifest file.

    Manifest must have been created by search_sounds or the CLI.
    Uses checkpoint-resume: sounds already downloaded are skipped
    (unless *overwrite* is True).

    Args:
        manifest: Path to the manifest.jsonl file.
        dest_dir: Output directory (default "out").
        resume: Skip already-downloaded sounds (default True).
        overwrite: Re-download even if present.
        fail_fast: Stop at first error.
        providers: Injectable provider instances (for testing).

    Returns:
        ``{"ok": True, "downloaded": N, "skipped": N, "failed": N}``
        or ``{"ok": False, "error": "message"}``.
    """
    from . import api

    try:
        refs = api.refs_from_manifest(manifest, skip_downloaded=False)
        if not refs:
            return {
                "ok": True,
                "downloaded": 0,
                "skipped": 0,
                "failed": 0,
                "message": "no pending sounds",
            }
        results = api.download(
            refs,
            dest_dir=dest_dir,
            manifest=manifest,
            resume=resume,
            overwrite=overwrite,
            fail_fast=fail_fast,
            providers=providers,
        )
        downloaded = sum(1 for r in results if r.status == "downloaded")
        skipped = sum(1 for r in results if r.status == "skipped")
        failed = sum(1 for r in results if r.status == "error")
        return {
            "ok": True,
            "downloaded": downloaded,
            "skipped": skipped,
            "failed": failed,
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def tool_check_provider_status(
    provider: str = "freesound",
    *,
    specs: dict | None = None,
) -> dict[str, Any]:
    """Check the configuration status of a sound provider.

    Reports whether API keys, auth tokens, or required packages are present.

    Args:
        provider: Provider name (e.g. "freesound", "archive", "video").
        specs: Injectable ProviderSpec dict (defaults to cli.SPECS).

    Returns:
        ``{"ok": True, "provider": str, "status": {"key": {"configured": bool, ...}}}``
        or ``{"ok": True, "provider": str, "hint": str}`` for no-auth providers.
    """
    try:
        if specs is None:
            from .cli import SPECS

            specs = SPECS

        spec = specs.get(provider)
        if spec is None:
            return {
                "ok": False,
                "error": f"unknown provider {provider!r}; "
                f"known: {', '.join(sorted(specs))}",
            }

        # Providers like "archive" need no auth — just return the hint.
        if spec.status_hint:
            return {"ok": True, "provider": provider, "hint": spec.status_hint}

        prov = spec.build()
        raw_status = prov.status() if hasattr(prov, "status") else {}

        labels = spec.status_labels
        missing_hint = spec.status_missing_hint
        result_status: dict[str, dict[str, Any]] = {}

        for key, present in raw_status.items():
            label = labels.get(key, key)
            entry: dict[str, Any] = {"configured": bool(present)}
            if not present and key in missing_hint:
                entry["hint"] = missing_hint[key]
            result_status[label] = entry

        return {"ok": True, "provider": provider, "status": result_status}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def tool_list_sources(
    specs: dict | None = None,
) -> dict[str, Any]:
    """List all registered sound source providers.

    Returns available providers with their help text.

    Args:
        specs: Injectable ProviderSpec dict (defaults to cli.SPECS).

    Returns:
        ``{"ok": True, "sources": [{"name": str, "help": str}...]}``
    """
    try:
        if specs is None:
            from .cli import SPECS

            specs = SPECS

        from .core.provider import provider_names

        sources = []
        for name in provider_names():
            spec = specs.get(name)
            sources.append({"name": name, "help": spec.help if spec else ""})
        return {"ok": True, "sources": sources}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# MCP server creation and run — the only place that imports the mcp SDK
# ---------------------------------------------------------------------------


def create_server(
    providers: dict | None = None,
    specs: dict | None = None,
):
    """Create an MCP server with soundfetch tools.

    Only this function imports the ``mcp`` SDK.  Requires
    ``pip install "soundfetch[mcp]"``.
    """
    try:
        from mcp.server import MCPServer  # mcp SDK v2 (2026-07+)
    except ImportError:
        try:
            from mcp.server.fastmcp import FastMCP as MCPServer  # mcp SDK v1
        except ImportError:
            raise ImportError(
                "MCP server requires the 'mcp' package. "
                'Install it with: pip install "soundfetch[mcp]"'
            ) from None

    server = MCPServer("soundfetch")

    @server.tool()
    async def search_sounds(
        query: str,
        provider: str = "freesound",
        license: str | None = None,
        max_results: int = 50,
        manifest: str | None = None,
    ) -> str:
        """Search a sound provider and return results."""
        result = tool_search_sounds(
            query,
            provider=provider,
            license=license,
            max_results=max_results,
            manifest=manifest,
            providers=providers,
        )
        return json.dumps(result, indent=2)

    @server.tool()
    async def download_manifest(
        manifest: str,
        dest_dir: str = "out",
        resume: bool = True,
        overwrite: bool = False,
        fail_fast: bool = False,
    ) -> str:
        """Download sounds from an existing manifest file."""
        result = tool_download_manifest(
            manifest,
            dest_dir=dest_dir,
            resume=resume,
            overwrite=overwrite,
            fail_fast=fail_fast,
            providers=providers,
        )
        return json.dumps(result, indent=2)

    @server.tool()
    async def check_provider_status(provider: str = "freesound") -> str:
        """Check the configuration status of a sound provider."""
        result = tool_check_provider_status(provider, specs=specs)
        return json.dumps(result, indent=2)

    @server.tool()
    async def list_sources() -> str:
        """List all registered sound source providers."""
        result = tool_list_sources(specs=specs)
        return json.dumps(result, indent=2)

    return server


def run():
    """Run the soundfetch MCP server over stdio."""
    server = create_server()
    server.run()
