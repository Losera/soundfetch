"""soundfetch CLI — spec-driven click wrapper over the soundfetch API.

Commands are generated from a small per-provider ``ProviderSpec``, so
adding a source is one spec entry instead of a copy-pasted command group.
Provider imports stay inside the ``build`` callables so
``soundfetch --help`` never imports requests / yt-dlp.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import click

from . import __version__

log = logging.getLogger(__name__)

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


# ---------------------------------------------------------------------------
# ProviderSpec — declarative per-provider config for the CLI factory
# ---------------------------------------------------------------------------

_DOWNLOAD_CONTROL = ("resume", "overwrite", "rate_delay", "rate", "workers", "fail_fast")


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    help: str
    default_outdir: str
    # Lazy provider factory: **opts → Provider (imports happen inside).
    build: Callable[..., Any]
    # Generic filter flags this provider supports (subset of common set).
    filters: tuple[str, ...] = ("license",)
    # Extra flags present only on `search` (e.g. sort, with_descriptors).
    search_only: tuple[str, ...] = ()
    # Extra flags present only on `download` (e.g. mode, quality, format).
    download_only: tuple[str, ...] = ()
    # Restrict --license to a Choice; None → free-form string.
    license_choices: tuple[str, ...] | None = None
    # Status display config.
    status_labels: dict[str, str] = field(default_factory=dict)
    status_missing_hint: dict[str, str] = field(default_factory=dict)
    status_hint: str = ""
    # Extra click commands attached to this provider group (e.g. auth).
    extra_commands: dict[str, click.Command] = field(default_factory=dict)
    # Optional help overrides.
    search_help: str | None = None
    download_help: str = (
        "Download sounds: from a QUERY, or from --manifest FILE."
    )
    license_help: str | None = None


# ---------------------------------------------------------------------------
# Central option definitions (name → click.Option kwargs)
# ---------------------------------------------------------------------------

OPTION_DEFS: dict[str, dict[str, Any]] = {
    "license": {"multiple": True, "help": "License short code (repeatable)."},
    "duration": {"help": "Raw Solr range, e.g. '[1 TO 30]'."},
    "tag": {"multiple": True, "help": "Require this tag (repeatable)."},
    "gen_ai": {
        "type": click.Choice(["allow", "deny", "unspecified", "any"]),
        "help": "Filter by Freesound gen_ai_preference.",
    },
    "raw_filter": {"help": "Pass-through filter clause (advanced)."},
    "sort": {"help": "Sort order (provider-specific)."},
    "page_size": {
        "default": 50,
        "show_default": True,
        "type": click.INT,
        "help": "Results per page.",
    },
    "max_results": {
        "default": None,
        "type": click.INT,
        "help": "Stop after N results (default: all pages).",
    },
    "manifest": {
        "type": click.Path(),
        "help": "Download from this manifest file instead of a QUERY.",
    },
    "resume": {
        "flags": ["--resume/--no-resume"],
        "is_flag": True,
        "default": True,
        "show_default": True,
        "help": "Skip sounds already downloaded in the manifest.",
    },
    "overwrite": {"is_flag": True, "help": "Re-download even if present."},
    "rate_delay": {
        "default": 0.5,
        "show_default": True,
        "type": click.FLOAT,
        "help": "Seconds between requests.",
    },
    "rate": {
        "default": None,
        "type": click.FLOAT,
        "help": "Max requests/sec via token-bucket pacing (overrides --rate-delay).",
    },
    "workers": {
        "default": 1,
        "show_default": True,
        "type": click.INT,
        "help": "Parallel download threads (default 1 = sequential).",
    },
    "fail_fast": {"is_flag": True, "help": "Stop at the first download error."},
    "mode": {
        "type": click.Choice(["preview", "original"]),
        "default": "preview",
        "show_default": True,
        "help": "Download previews or OAuth2-only originals.",
    },
    "quality": {
        "type": click.Choice(["hq", "lq"]),
        "default": "hq",
        "show_default": True,
        "help": "Preview quality.",
    },
    "format": {
        "type": click.Choice(["mp3", "ogg"]),
        "default": "mp3",
        "show_default": True,
        "help": "Preview format.",
    },
    "with_descriptors": {
        "help": "Comma list, e.g. bpm,pitch,spectral_centroid.",
    },
    "json": {"is_flag": True, "help": "Emit JSON on stdout."},
}


# ---------------------------------------------------------------------------
# Provider build functions (lazy imports inside each)
# ---------------------------------------------------------------------------


def _build_freesound(**opts: Any):
    from .providers.freesound.provider import FreesoundProvider

    return FreesoundProvider(
        mode=opts.get("mode", "preview"),
        preview_quality=opts.get("quality", "hq"),
        preview_format=opts.get("format", "mp3"),
    )


def _build_archive(**opts: Any):
    from .providers.archive.provider import ArchiveProvider

    return ArchiveProvider()


def _build_video(**opts: Any):
    from .providers.video.provider import VideoProvider

    return VideoProvider()


# ---------------------------------------------------------------------------
# Freesound-only auth command (genuinely provider-specific)
# ---------------------------------------------------------------------------


@click.command("auth", help="Run the Freesound OAuth2 browser flow (needed for original downloads).")
@click.option("--client-id", "client_id", default=None, envvar="FREESOUND_CLIENT_ID")
@click.option("--client-secret", "client_secret", default=None, envvar="FREESOUND_CLIENT_SECRET")
@click.option("--redirect-uri", "redirect_uri", default="http://localhost:8765/callback", show_default=True)
@click.option("--refresh", is_flag=True, help="Force token refresh (ignore cached token).")
def freesound_auth(
    client_id: str | None,
    client_secret: str | None,
    redirect_uri: str,
    refresh: bool,
) -> None:
    from .providers.freesound.auth import AuthError, OAuthClient, TokenStore, DEFAULT_CONFIG_DIR

    if not client_id or not client_secret:
        raise click.UsageError(
            "FREESOUND_CLIENT_ID and FREESOUND_CLIENT_SECRET are required. "
            "Set them as env vars, in .env, or via --client-id/--client-secret."
        )
    api_key = os.environ.get("FREESOUND_API_KEY")
    if api_key and client_secret == api_key:
        click.echo(
            click.style(
                "warning: FREESOUND_CLIENT_SECRET looks identical to FREESOUND_API_KEY. "
                "These are different credentials — the secret is the OAuth app secret from "
                "https://freesound.org/apiv2/apps/ (not your API key).",
                fg="yellow",
            )
        )
    config_dir = Path(os.environ.get("SOUNDFETCH_CONFIG_DIR", DEFAULT_CONFIG_DIR))
    store = TokenStore(config_dir / "freesound.json")
    client = OAuthClient(client_id, client_secret, redirect_uri=redirect_uri, store=store)
    try:
        if refresh:
            client.get_token(refresh=True)
            click.echo(f"token refreshed and cached at {store.path}")
        else:
            token = client.run_code_flow()
            click.echo(f"authorized; token cached at {store.path} (expires in ~{int(token.expires_at)}s)")
    except AuthError as exc:
        raise click.ClickException(str(exc))


# ---------------------------------------------------------------------------
# ProviderSpec instances
# ---------------------------------------------------------------------------

SPECS: dict[str, ProviderSpec] = {
    "freesound": ProviderSpec(
        name="freesound",
        help="Freesound.org source.",
        default_outdir="./freesound-out",
        build=_build_freesound,
        filters=("license", "duration", "tag", "gen_ai", "raw_filter"),
        search_only=("sort", "with_descriptors"),
        download_only=("mode", "quality", "format"),
        license_choices=("cc0", "cc-by", "cc-by-sa", "cc-by-nc", "any"),
        search_help="Search Freesound and write a manifest (no downloads).",
        status_labels={
            "api_key": "api_key",
            "client_id": "client_id",
            "client_secret": "client_secret",
            "oauth_token": "oauth_token",
            "oauth_token_expired": "oauth_token",
        },
        status_missing_hint={
            "oauth_token_expired": "cached token is expired — run `soundfetch freesound auth --refresh`",
        },
        extra_commands={"auth": freesound_auth},
    ),
    "archive": ProviderSpec(
        name="archive",
        help="Internet Archive source.",
        default_outdir="./archive-out",
        build=_build_archive,
        filters=("license", "tag", "raw_filter"),
        search_only=("sort",),
        license_choices=("cc0", "cc-by", "cc-by-sa", "cc-by-nc", "any"),
        search_help="Search Internet Archive and write a manifest (no downloads).",
        status_hint="no configuration required (Internet Archive downloads need no auth)",
    ),
    "video": ProviderSpec(
        name="video",
        help="Video source (yt-dlp-based) — audio-only extraction from a URL or search.",
        default_outdir="./video-out",
        build=_build_video,
        filters=("license",),
        license_choices=("cc-by", "any"),
        search_help=(
            "Search or resolve videos and write a manifest (no downloads).\n\n"
            "QUERY is either a search term (searched on YouTube) or a video, "
            "playlist, or channel URL."
        ),
        license_help=(
            "Best-effort only: YouTube's license field is free text, not an enum, "
            "so only 'cc-by' is actually checked."
        ),
        status_labels={"yt_dlp_installed": "yt_dlp"},
        status_missing_hint={
            "yt_dlp_installed": 'run `pip install "soundfetch[video]"`'
        },
    ),
}


# ---------------------------------------------------------------------------
# Click option / argument factories
# ---------------------------------------------------------------------------


def _opt(spec: ProviderSpec, name: str) -> click.Option:
    defs = dict(OPTION_DEFS[name])
    flags: list[str] = defs.pop("flags", [f"--{name.replace('_', '-')}"])
    # Per-spec overrides.
    if name == "license":
        if spec.license_choices:
            defs["type"] = click.Choice(spec.license_choices)
        if spec.license_help:
            defs["help"] = spec.license_help
    return click.Option(flags, **defs)


def _make_params(spec: ProviderSpec, kind: str) -> list[click.Parameter]:
    params: list[click.Parameter] = [
        click.Argument(
            ["query"],
            required=(kind == "search"),
            metavar="QUERY",
        ),
        click.Option(
            ["-o", "--outdir"],
            default=spec.default_outdir,
            show_default=True,
            type=click.Path(),
            help="Output directory.",
        ),
    ]
    if kind == "download":
        params.append(_opt(spec, "manifest"))
    # Generic filter flags.
    for fname in spec.filters:
        params.append(_opt(spec, fname))
    # Provider-specific extra flags.
    if kind == "search":
        for fname in spec.search_only:
            params.append(_opt(spec, fname))
    else:
        for fname in spec.download_only:
            params.append(_opt(spec, fname))
        for fname in _DOWNLOAD_CONTROL:
            params.append(_opt(spec, fname))
    # Common paging options (order: page_size then max_results for search,
    # reversed for download to match historical CLI feel).
    if kind == "search":
        params.append(_opt(spec, "page_size"))
        params.append(_opt(spec, "max_results"))
        # Machine-readable output — search only (download stays human).
        params.append(_opt(spec, "json"))
    else:
        params.append(_opt(spec, "max_results"))
        params.append(_opt(spec, "page_size"))
    return params


# ---------------------------------------------------------------------------
# Generic command bodies (shared by every provider)
# ---------------------------------------------------------------------------


def _json_enabled(ctx: click.Context | None, opts: dict[str, Any]) -> bool:
    """True when --json was given on the subcommand or the root group."""
    return bool(opts.get("json")) or bool(ctx and ctx.obj.get("json"))


def _emit_json(payload: dict[str, Any]) -> None:
    click.echo(json.dumps(payload, indent=2, default=str))


def _json_error(exc: BaseException) -> None:
    """Emit a ``{"ok": false, "error": {...}}`` payload and exit nonzero."""
    click.echo(
        json.dumps(
            {
                "ok": False,
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            },
            indent=2,
        )
    )
    sys.exit(getattr(exc, "exit_code", 1))


def _search_extra(spec: ProviderSpec, opts: dict[str, Any]) -> dict[str, Any]:
    extra: dict[str, Any] = {"page": 1}
    desc = opts.get("with_descriptors")
    if desc:
        extra["with_descriptors"] = [
            d.strip() for d in desc.split(",") if d.strip()
        ]
    return extra


def _run_search(name: str, ctx: click.Context | None, **opts: Any) -> None:
    from . import api

    spec = SPECS[name]
    outdir = Path(opts["outdir"])
    manifest = outdir / "manifest.jsonl"
    json_mode = _json_enabled(ctx, opts)

    try:
        provider = spec.build(**opts)
        refs = api.search(
            opts["query"],
            provider=spec.name,
            providers={spec.name: provider},
            license=opts.get("license"),
            duration=opts.get("duration"),
            tag=opts.get("tag"),
            gen_ai=opts.get("gen_ai"),
            raw_filter=opts.get("raw_filter"),
            sort=opts.get("sort"),
            page_size=opts["page_size"],
            max_results=opts["max_results"],
            extra=_search_extra(spec, opts),
            # Suppress the "page N:" progress lines in JSON mode — they'd
            # corrupt stdout.
            on_page=(
                None
                if json_mode
                else lambda result, page: click.echo(
                    f"page {page}: {len(result.results)} results (total {result.total})"
                )
            ),
        )
        api.save_search(refs, manifest)
    except click.ClickException as exc:
        if json_mode:
            _json_error(exc)
        raise
    except Exception as exc:
        if json_mode:
            _json_error(exc)
        raise

    payload: dict[str, Any] = {
        "ok": True,
        "command": "search",
        "provider": spec.name,
        "query": opts["query"],
        "manifest": str(manifest),
        "count": len(refs),
        "results": [asdict(r) for r in refs],
    }
    if json_mode:
        _emit_json(payload)
        return
    click.echo(f"wrote {len(refs)} sound references to {manifest}")


def _run_download(name: str, **opts: Any) -> None:
    from . import api

    spec = SPECS[name]
    outdir = Path(opts["outdir"])
    manifest_arg: str | None = opts.get("manifest")
    manifest = Path(manifest_arg) if manifest_arg else outdir / "manifest.jsonl"
    query: str | None = opts.get("query")
    provider = spec.build(**opts)

    if query:
        refs = api.search(
            query,
            provider=spec.name,
            providers={spec.name: provider},
            license=opts.get("license"),
            duration=opts.get("duration"),
            tag=opts.get("tag"),
            gen_ai=opts.get("gen_ai"),
            raw_filter=opts.get("raw_filter"),
            page_size=opts["page_size"],
            max_results=opts["max_results"],
            extra=_search_extra(spec, opts),
        )
        if not manifest_arg:
            api.save_search(refs, manifest)
        click.echo(f"found {len(refs)} sounds")
    elif manifest_arg:
        refs = api.refs_from_manifest(manifest)
        click.echo(f"loaded {len(refs)} sounds from {manifest}")
    else:
        raise click.UsageError("provide a QUERY or --manifest FILE")

    pacing = None
    rate = opts.get("rate")
    if rate:
        from .core.pacing import Pacing

        pacing = Pacing(rates={spec.name: float(rate)})

    results = api.download(
        refs,
        dest_dir=outdir,
        manifest=manifest,
        resume=opts["resume"],
        overwrite=opts["overwrite"],
        fail_fast=opts["fail_fast"],
        rate_delay=opts["rate_delay"],
        workers=opts["workers"],
        pacing=pacing,
        providers={spec.name: provider},
    )
    _report_downloads(results)


def _run_status(name: str, ctx: click.Context | None, **opts: Any) -> None:
    spec = SPECS[name]
    json_mode = _json_enabled(ctx, opts)

    try:
        if spec.status_hint:
            payload: dict[str, Any] = {
                "ok": True,
                "provider": name,
                "hint": spec.status_hint,
            }
            human = spec.status_hint
        else:
            provider = spec.build()
            status: dict[str, Any] = {}
            lines: list[str] = []
            for key, present in provider.status().items():
                label = spec.status_labels.get(key, key)
                if key.endswith("_expired"):
                    # Inverted signal: True means "bad". Shown as `expired`.
                    status[label] = {"expired": bool(present)}
                    if present:
                        hint = spec.status_missing_hint.get(key)
                        if hint:
                            status[label]["hint"] = hint
                        lines.append(f"{label}: expired" + (f" ({hint})" if hint else ""))
                    continue
                status[label] = {"configured": bool(present)}
                if present:
                    lines.append(f"{label}: configured")
                else:
                    hint = spec.status_missing_hint.get(key)
                    if hint:
                        status[label]["hint"] = hint
                    lines.append(f"{label}: missing" + (f" ({hint})" if hint else ""))
            payload = {"ok": True, "provider": name, "status": status}
            human = "\n".join(lines)
    except Exception as exc:
        if json_mode:
            _json_error(exc)
        raise

    if json_mode:
        _emit_json(payload)
    else:
        click.echo(human)


def _report_downloads(results) -> None:
    ok = sum(1 for r in results if r.status == "downloaded")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "error")
    click.echo(f"downloaded={ok} skipped={skipped} failed={failed}")
    if failed:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Group / command factory
# ---------------------------------------------------------------------------


def _make_group(spec: ProviderSpec) -> click.Group:
    group = click.Group(name=spec.name, help=spec.help)

    search_help = spec.search_help or (
        f"Search {spec.name} and write a manifest (no downloads)."
    )
    group.add_command(
        click.Command(
            name="search",
            params=_make_params(spec, "search"),
            # click.pass_context injects the subcommand context so a root-level
            # --json reaches _run_search even when the flag is placed before
            # the provider group (e.g. `soundfetch --json freesound search`).
            callback=click.pass_context(
                lambda ctx, _n=spec.name, **o: _run_search(_n, ctx, **o)
            ),
            help=search_help,
        )
    )
    group.add_command(
        click.Command(
            name="download",
            params=_make_params(spec, "download"),
            callback=lambda _n=spec.name, **o: _run_download(_n, **o),
            help=spec.download_help,
        )
    )
    group.add_command(
        click.Command(
            name="status",
            params=[_opt(spec, "json")],
            callback=click.pass_context(
                lambda ctx, _n=spec.name, **o: _run_status(_n, ctx, **o)
            ),
            help="Show what's configured for this source.",
        )
    )
    for cmd_name, cmd in spec.extra_commands.items():
        group.add_command(cmd)
    return group


# ---------------------------------------------------------------------------
# Root CLI
# ---------------------------------------------------------------------------


def _load_dotenv() -> None:
    """Load .env from cwd if present (best-effort)."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(version=__version__)
@click.option("--verbose", is_flag=True, help="Debug logging.")
@click.option("--json", "json_mode", is_flag=True, help="Emit JSON on stdout.")
@click.pass_context
def main(ctx: click.Context, verbose: bool, json_mode: bool) -> None:
    """soundfetch: batch sound/data collection across the internet."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    ctx.ensure_object(dict)
    _load_dotenv()
    ctx.obj["verbose"] = verbose
    ctx.obj["json"] = json_mode


@main.command("sources")
@click.option("--json", "json_mode", is_flag=True, help="Emit JSON on stdout.")
@click.pass_context
def sources(ctx: click.Context, json_mode: bool) -> None:
    """List registered providers."""
    from .core.provider import provider_names as _provider_names

    json_mode = json_mode or bool(ctx.obj.get("json"))
    sources = [
        {"name": name, "help": SPECS[name].help if name in SPECS else ""}
        for name in _provider_names()
    ]
    if json_mode:
        _emit_json({"ok": True, "sources": sources})
        return
    for source in sources:
        click.echo(f"{source['name']} — {source['help']}" if source["help"] else source["name"])


@main.command("mcp")
def mcp() -> None:
    """Run the soundfetch MCP server over stdio.

    Exposes ``search_sounds``, ``download_manifest``, ``check_provider_status``,
    and ``list_sources`` as Model Context Protocol tools for agents.
    Requires ``pip install "soundfetch[mcp]"``.
    """
    try:
        from .mcp import run
    except ImportError as exc:
        raise click.ClickException(
            'the MCP server requires the "mcp" package — '
            'install it with `pip install "soundfetch[mcp]"`'
        ) from exc
    run()


# Register provider groups.
for _name, _spec in SPECS.items():
    main.add_command(_make_group(_spec))

if __name__ == "__main__":
    main()
