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

from pathlib import Path
from typing import Any

MAX_AGENT_RESULTS = 50

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
    gen_ai: str | None = None,
    tag: str | None = None,
    duration: str | None = None,
    max_results: int = 20,
    manifest: str | None = None,
    providers: dict | None = None,
) -> dict[str, Any]:
    """Search a sound provider and return results as JSON-serializable dicts.

    Args:
        query: Search query string (e.g. "piano", "rain storm").
        provider: Provider name (e.g. "freesound", "archive", "video").
        license: Optional license filter (e.g. "cc0", "cc-by").
        gen_ai: Optional Freesound generative-AI preference filter.
        tag: Optional provider tag/subject filter.
        duration: Optional provider duration filter.
        max_results: Maximum number of compact results (default 20, max 50).
        manifest: Optional path to save results to a manifest file.
        providers: Injectable provider instances (for testing).

    Returns:
        ``{"ok": True, "count": int, "results": [...]}``
        or with ``"manifest": str`` if *manifest* was given.
        ``{"ok": False, "error": "message"}`` on failure.
    """
    from . import api

    try:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= max_results <= MAX_AGENT_RESULTS:
            raise ValueError(f"max_results must be between 1 and {MAX_AGENT_RESULTS}")
        refs = api.search(
            query.strip(),
            provider=provider,
            providers=providers,
            license=license,
            gen_ai=gen_ai,
            tag=tag,
            duration=duration,
            max_results=max_results,
        )
        result: dict[str, Any] = {
            "ok": True,
            "count": len(refs),
            "results": [_compact_ref(r) for r in refs],
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
    workers: int = 1,
    rate: float | None = None,
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
        manifest_path = Path(manifest)
        if not manifest_path.is_file():
            raise ValueError(f"manifest is not a file: {manifest}")
        if workers < 1:
            raise ValueError("workers must be at least 1")
        if rate is not None and rate <= 0:
            raise ValueError("rate must be greater than 0")
        refs = api.refs_from_manifest(manifest_path, skip_downloaded=False)
        pacing = None
        if rate is not None:
            from .core.pacing import Pacing

            pacing = Pacing(rates={})
            for ref in refs:
                pacing.set_rate(ref.provider, rate)
        if not refs:
            return {
                "ok": True,
                "status": "success",
                "downloaded": 0,
                "skipped": 0,
                "failed": 0,
                "errors": [],
                "message": "no pending sounds",
            }
        results = api.download(
            refs,
            dest_dir=dest_dir,
            manifest=manifest,
            resume=resume,
            overwrite=overwrite,
            fail_fast=fail_fast,
            workers=workers,
            pacing=pacing,
            providers=providers,
        )
        downloaded = sum(1 for r in results if r.status == "downloaded")
        skipped = sum(1 for r in results if r.status == "skipped")
        failed = sum(1 for r in results if r.status == "error")
        errors = [r.error for r in results if r.status == "error" and r.error]
        return {
            "ok": failed == 0,
            "status": "success" if failed == 0 else "partial",
            "downloaded": downloaded,
            "skipped": skipped,
            "failed": failed,
            "errors": errors[:10],
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _compact_ref(ref) -> dict[str, Any]:
    """Return the stable, token-conscious projection exposed to agents."""
    metadata = ref.metadata or {}
    return {
        "provider": ref.provider,
        "provider_id": ref.provider_id,
        "name": ref.name,
        "url": ref.url,
        "file_format": ref.file_format,
        "license": metadata.get("license") or metadata.get("licenseurl"),
        "duration": metadata.get("duration"),
        "tags": metadata.get("tags") or metadata.get("subject"),
        "gen_ai_preference": metadata.get("gen_ai_preference"),
    }


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
        from mcp.server.fastmcp import FastMCP as MCPServer
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
        gen_ai: str | None = None,
        tag: str | None = None,
        duration: str | None = None,
        max_results: int = 20,
        manifest: str | None = None,
    ) -> dict[str, Any]:
        """Search a sound provider and return results."""
        result = tool_search_sounds(
            query,
            provider=provider,
            license=license,
            gen_ai=gen_ai,
            tag=tag,
            duration=duration,
            max_results=max_results,
            manifest=manifest,
            providers=providers,
        )
        return result

    @server.tool()
    async def download_manifest(
        manifest: str,
        dest_dir: str = "out",
        resume: bool = True,
        overwrite: bool = False,
        fail_fast: bool = False,
        workers: int = 1,
        rate: float | None = None,
    ) -> dict[str, Any]:
        """Download sounds from an existing manifest file."""
        result = tool_download_manifest(
            manifest,
            dest_dir=dest_dir,
            resume=resume,
            overwrite=overwrite,
            fail_fast=fail_fast,
            workers=workers,
            rate=rate,
            providers=providers,
        )
        return result

    @server.tool()
    async def check_provider_status(provider: str = "freesound") -> dict[str, Any]:
        """Check the configuration status of a sound provider."""
        result = tool_check_provider_status(provider, specs=specs)
        return result

    @server.tool()
    async def list_sources() -> dict[str, Any]:
        """List all registered sound source providers."""
        result = tool_list_sources(specs=specs)
        return result

    return server


def run():
    """Run the soundfetch MCP server over stdio."""
    server = create_server()
    server.run()
