"""soundfetch CLI — provider-first click surface."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import click

from . import __version__
from .core.provider import get_provider, provider_names

log = logging.getLogger(__name__)

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(version=__version__)
@click.option("--verbose", is_flag=True, help="Debug logging.")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """soundfetch: batch sound/data collection across the internet."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    ctx.ensure_object(dict)
    _load_dotenv()
    ctx.obj["verbose"] = verbose


def _load_dotenv() -> None:
    """Load .env from cwd if present (best-effort)."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def _provider(name: str):
    """Build a provider instance, resolving env config."""
    return get_provider(name)


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------


@main.command("sources")
def sources() -> None:
    """List registered providers."""
    for name in provider_names():
        click.echo(name)


# ---------------------------------------------------------------------------
# freesound
# ---------------------------------------------------------------------------


@main.group()
def freesound() -> None:
    """Freesound.org source."""


def _freesound_provider(mode: str, quality: str, fmt: str):
    from .providers.freesound.provider import FreesoundProvider

    return FreesoundProvider(mode=mode, preview_quality=quality, preview_format=fmt)


def _filters(
    licenses: tuple[str, ...],
    duration: str | None,
    tags: tuple[str, ...],
    gen_ai: str | None,
    raw_filter: str | None,
) -> dict[str, str]:
    result: dict[str, str] = {}
    if licenses:
        result["license"] = ",".join(licenses)
    if duration:
        result["duration"] = duration
    if tags:
        result["tag"] = ",".join(tags)
    if gen_ai:
        result["gen_ai"] = gen_ai
    if raw_filter:
        result["raw"] = raw_filter
    return result


@freesound.command("search")
@click.argument("query")
@click.option("-o", "--outdir", default="./freesound-out", show_default=True, type=click.Path())
@click.option("--license", "licenses", multiple=True, type=click.Choice(["cc0", "cc-by", "cc-by-sa", "cc-by-nc", "any"]))
@click.option("--duration", default=None, help="Raw Solr range, e.g. '[1 TO 30]'.")
@click.option("--tag", "tags", multiple=True, help="Require this tag (repeatable).")
@click.option("--gen-ai", "gen_ai", default=None, type=click.Choice(["allow", "deny", "unspecified", "any"]))
@click.option("--raw-filter", "raw_filter", default=None, help="Pass-through Solr filter (advanced).")
@click.option("--sort", "sort", default=None, help="Sort: score|duration_desc|...")
@click.option("--page-size", default=50, show_default=True, type=int)
@click.option("--max-results", default=None, type=int, help="Stop after N results (default: all pages).")
@click.option("--with-descriptors", "with_descriptors", default=None, help="Comma list, e.g. bpm,pitch,spectral_centroid (mfcc opt-in).")
def freesound_search(
    query: str,
    outdir: str,
    licenses: tuple[str, ...],
    duration: str | None,
    tags: tuple[str, ...],
    gen_ai: str | None,
    raw_filter: str | None,
    sort: str | None,
    page_size: int,
    max_results: int | None,
    with_descriptors: str | None,
) -> None:
    """Search Freesound and write a manifest (no downloads)."""
    from .core.engine import search_all, write_search_records
    from .core.model import SearchParams

    provider = _freesound_provider(mode="preview", quality="hq", fmt="mp3")
    outdir_path = Path(outdir)
    manifest = outdir_path / "manifest.jsonl"

    params = SearchParams(
        query=query,
        filters=_filters(licenses, duration, tags, gen_ai, raw_filter),
        page_size=page_size,
        max_results=max_results,
        sort=sort,
        extra={"page": 1},
    )
    if with_descriptors:
        params.extra["with_descriptors"] = [d.strip() for d in with_descriptors.split(",") if d.strip()]

    refs = search_all(
        provider,
        params,
        on_page=lambda result, page: click.echo(
            f"page {page}: {len(result.results)} results (total {result.total})"
        ),
    )

    write_search_records(manifest, refs, total=_last_total(refs))
    click.echo(f"wrote {len(refs)} sound references to {manifest}")


def _last_total(refs) -> int:
    return len(refs)


@freesound.command("download")
@click.argument("query", required=False)
@click.option("--manifest", "manifest_arg", default=None, type=click.Path())
@click.option("-o", "--outdir", default="./freesound-out", show_default=True, type=click.Path())
@click.option("--mode", "mode", default="preview", type=click.Choice(["preview", "original"]), show_default=True)
@click.option("--quality", "quality", default="hq", type=click.Choice(["hq", "lq"]), show_default=True)
@click.option("--format", "fmt", default="mp3", type=click.Choice(["mp3", "ogg"]), show_default=True)
@click.option("--license", "licenses", multiple=True, type=click.Choice(["cc0", "cc-by", "cc-by-sa", "cc-by-nc", "any"]))
@click.option("--duration", default=None, help="Raw Solr range, e.g. '[1 TO 30]'.")
@click.option("--tag", "tags", multiple=True)
@click.option("--gen-ai", "gen_ai", default=None, type=click.Choice(["allow", "deny", "unspecified", "any"]))
@click.option("--raw-filter", "raw_filter", default=None)
@click.option("--max-results", default=None, type=int)
@click.option("--page-size", default=50, show_default=True, type=int)
@click.option("--resume/--no-resume", default=True, show_default=True, help="Skip sounds already downloaded in the manifest.")
@click.option("--overwrite", is_flag=True, help="Re-download even if present.")
@click.option("--rate-delay", "rate_delay", default=0.5, show_default=True, type=float, help="Seconds between requests.")
@click.option("--fail-fast", is_flag=True, help="Stop at the first download error.")
def freesound_download(
    query: str | None,
    manifest_arg: str | None,
    outdir: str,
    mode: str,
    quality: str,
    fmt: str,
    licenses: tuple[str, ...],
    duration: str | None,
    tags: tuple[str, ...],
    gen_ai: str | None,
    raw_filter: str | None,
    max_results: int | None,
    page_size: int,
    resume: bool,
    overwrite: bool,
    rate_delay: float,
    fail_fast: bool,
) -> None:
    """Download sounds: from a QUERY, or from --manifest FILE."""
    from .core.engine import download_refs, search_all, write_search_records
    from .core.manifest import read_records
    from .core.model import SearchParams, SoundRef

    outdir_path = Path(outdir)
    manifest = Path(manifest_arg) if manifest_arg else outdir_path / "manifest.jsonl"

    provider = _freesound_provider(mode=mode, quality=quality, fmt=fmt)

    # Two inputs are valid: QUERY (search-then-download) or --manifest (download
    # previously listed sounds). Exactly one is required.
    if query:
        params = SearchParams(
            query=query,
            filters=_filters(licenses, duration, tags, gen_ai, raw_filter),
            page_size=page_size,
            max_results=max_results,
            extra={"page": 1},
        )
        refs = search_all(provider, params)
        if not manifest_arg:
            write_search_records(manifest, refs, total=len(refs))
        click.echo(f"found {len(refs)} sounds")
    elif manifest_arg:
        refs = _refs_from_manifest(manifest)
        click.echo(f"loaded {len(refs)} sounds from {manifest}")
    else:
        raise click.UsageError("provide a QUERY or --manifest FILE")

    results = download_refs(
        provider,
        refs,
        outdir_path,
        manifest,
        resume=resume,
        overwrite=overwrite,
        fail_fast=fail_fast,
        rate_delay=rate_delay,
    )
    _report_downloads(results)


def _refs_from_manifest(manifest: Path) -> list[SoundRef]:
    from .core.manifest import iter_latest
    from .core.model import SoundRef

    refs: list[SoundRef] = []
    for record in iter_latest(manifest):
        if record.get("status") == "downloaded" and record.get("local_file"):
            continue  # already have it; download loop would skip anyway
        refs.append(
            SoundRef(
                provider=record.get("provider", ""),
                provider_id=str(record.get("provider_id", "")),
                name=record.get("name", ""),
                url=record.get("url", ""),
                download_url=record.get("download_url"),
                file_format=record.get("file_format"),
                checksum=record.get("checksum"),
                metadata=record.get("metadata") or {},
            )
        )
    return refs


def _report_downloads(results) -> None:
    ok = sum(1 for r in results if r.status == "downloaded")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "error")
    click.echo(f"downloaded={ok} skipped={skipped} failed={failed}")
    if failed:
        sys.exit(1)


@freesound.command("auth")
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
    """Run the Freesound OAuth2 browser flow (needed for original downloads)."""
    from .providers.freesound.auth import AuthError, OAuthClient, TokenStore, DEFAULT_CONFIG_DIR

    if not client_id or not client_secret:
        raise click.UsageError(
            "FREESOUND_CLIENT_ID and FREESOUND_CLIENT_SECRET are required. "
            "Set them as env vars, in .env, or via --client-id/--client-secret."
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


@freesound.command("status")
def freesound_status() -> None:
    """Show what's configured for the Freesound source."""
    from .providers.freesound.provider import FreesoundProvider

    provider = FreesoundProvider()
    status = provider.status()
    for key, present in status.items():
        click.echo(f"{key}: {'configured' if present else 'missing'}")


# ---------------------------------------------------------------------------
# archive
# ---------------------------------------------------------------------------


@main.group()
def archive() -> None:
    """Internet Archive source."""


def _archive_provider():
    from .providers.archive.provider import ArchiveProvider

    return ArchiveProvider()


def _archive_filters(
    licenses: tuple[str, ...], tags: tuple[str, ...], raw_filter: str | None
) -> dict[str, str]:
    result: dict[str, str] = {}
    if licenses:
        result["license"] = ",".join(licenses)
    if tags:
        result["tag"] = ",".join(tags)
    if raw_filter:
        result["raw"] = raw_filter
    return result


@archive.command("search")
@click.argument("query")
@click.option("-o", "--outdir", default="./archive-out", show_default=True, type=click.Path())
@click.option("--license", "licenses", multiple=True, type=click.Choice(["cc0", "cc-by", "cc-by-sa", "cc-by-nc", "any"]))
@click.option("--tag", "tags", multiple=True, help="Match this Internet Archive subject (repeatable).")
@click.option("--raw-filter", "raw_filter", default=None, help="Pass-through Lucene clause (advanced).")
@click.option("--sort", "sort", default=None, help="Sort, e.g. 'downloads desc'.")
@click.option("--page-size", default=50, show_default=True, type=int)
@click.option("--max-results", default=None, type=int, help="Stop after N results (default: all pages).")
def archive_search(
    query: str,
    outdir: str,
    licenses: tuple[str, ...],
    tags: tuple[str, ...],
    raw_filter: str | None,
    sort: str | None,
    page_size: int,
    max_results: int | None,
) -> None:
    """Search Internet Archive and write a manifest (no downloads)."""
    from .core.engine import search_all, write_search_records
    from .core.model import SearchParams

    provider = _archive_provider()
    outdir_path = Path(outdir)
    manifest = outdir_path / "manifest.jsonl"

    params = SearchParams(
        query=query,
        filters=_archive_filters(licenses, tags, raw_filter),
        page_size=page_size,
        max_results=max_results,
        sort=sort,
        extra={"page": 1},
    )
    refs = search_all(
        provider,
        params,
        on_page=lambda result, page: click.echo(
            f"page {page}: {len(result.results)} results (total {result.total})"
        ),
    )

    write_search_records(manifest, refs, total=len(refs))
    click.echo(f"wrote {len(refs)} sound references to {manifest}")


@archive.command("download")
@click.argument("query", required=False)
@click.option("--manifest", "manifest_arg", default=None, type=click.Path())
@click.option("-o", "--outdir", default="./archive-out", show_default=True, type=click.Path())
@click.option("--license", "licenses", multiple=True, type=click.Choice(["cc0", "cc-by", "cc-by-sa", "cc-by-nc", "any"]))
@click.option("--tag", "tags", multiple=True)
@click.option("--raw-filter", "raw_filter", default=None)
@click.option("--max-results", default=None, type=int)
@click.option("--page-size", default=50, show_default=True, type=int)
@click.option("--resume/--no-resume", default=True, show_default=True, help="Skip sounds already downloaded in the manifest.")
@click.option("--overwrite", is_flag=True, help="Re-download even if present.")
@click.option("--rate-delay", "rate_delay", default=0.5, show_default=True, type=float, help="Seconds between requests.")
@click.option("--fail-fast", is_flag=True, help="Stop at the first download error.")
def archive_download(
    query: str | None,
    manifest_arg: str | None,
    outdir: str,
    licenses: tuple[str, ...],
    tags: tuple[str, ...],
    raw_filter: str | None,
    max_results: int | None,
    page_size: int,
    resume: bool,
    overwrite: bool,
    rate_delay: float,
    fail_fast: bool,
) -> None:
    """Download sounds: from a QUERY, or from --manifest FILE."""
    from .core.engine import download_refs, search_all, write_search_records
    from .core.model import SearchParams

    outdir_path = Path(outdir)
    manifest = Path(manifest_arg) if manifest_arg else outdir_path / "manifest.jsonl"
    provider = _archive_provider()

    if query:
        params = SearchParams(
            query=query,
            filters=_archive_filters(licenses, tags, raw_filter),
            page_size=page_size,
            max_results=max_results,
            extra={"page": 1},
        )
        refs = search_all(provider, params)
        if not manifest_arg:
            write_search_records(manifest, refs, total=len(refs))
        click.echo(f"found {len(refs)} sounds")
    elif manifest_arg:
        refs = _refs_from_manifest(manifest)
        click.echo(f"loaded {len(refs)} sounds from {manifest}")
    else:
        raise click.UsageError("provide a QUERY or --manifest FILE")

    results = download_refs(
        provider,
        refs,
        outdir_path,
        manifest,
        resume=resume,
        overwrite=overwrite,
        fail_fast=fail_fast,
        rate_delay=rate_delay,
    )
    _report_downloads(results)


@archive.command("status")
def archive_status() -> None:
    """Show what's configured for the Internet Archive source."""
    click.echo("no configuration required (Internet Archive downloads need no auth)")


# ---------------------------------------------------------------------------
# video
# ---------------------------------------------------------------------------


@main.group()
def video() -> None:
    """Video source (yt-dlp-based) — audio-only extraction from a URL or search."""


def _video_provider():
    from .providers.video.provider import VideoProvider

    return VideoProvider()


def _video_filters(license_: str | None) -> dict[str, str]:
    return {"license": license_} if license_ else {}


_VIDEO_LICENSE_HELP = (
    "Best-effort only: YouTube's license field is free text, not an enum, so "
    "only 'cc-by' is actually checked."
)


@video.command("search")
@click.argument("query")
@click.option("-o", "--outdir", default="./video-out", show_default=True, type=click.Path())
@click.option("--license", "license_", default=None, type=click.Choice(["cc-by", "any"]), help=_VIDEO_LICENSE_HELP)
@click.option("--page-size", default=50, show_default=True, type=int)
@click.option(
    "--max-results",
    default=None,
    type=int,
    help="Cap on results. For a free-text QUERY this is also the total fetched up "
    "front (yt-dlp search has no pagination); default 50. Not a hard cap for a "
    "playlist/channel URL.",
)
def video_search(
    query: str,
    outdir: str,
    license_: str | None,
    page_size: int,
    max_results: int | None,
) -> None:
    """Search or resolve videos and write a manifest (no downloads).

    QUERY is either a search term (searched on YouTube) or a video, playlist,
    or channel URL.
    """
    from .core.engine import search_all, write_search_records
    from .core.model import SearchParams

    provider = _video_provider()
    outdir_path = Path(outdir)
    manifest = outdir_path / "manifest.jsonl"

    params = SearchParams(
        query=query,
        filters=_video_filters(license_),
        page_size=page_size,
        max_results=max_results,
        extra={"page": 1},
    )
    refs = search_all(
        provider,
        params,
        on_page=lambda result, page: click.echo(
            f"page {page}: {len(result.results)} results (total {result.total})"
        ),
    )

    write_search_records(manifest, refs, total=len(refs))
    click.echo(f"wrote {len(refs)} sound references to {manifest}")


@video.command("download")
@click.argument("query", required=False)
@click.option("--manifest", "manifest_arg", default=None, type=click.Path())
@click.option("-o", "--outdir", default="./video-out", show_default=True, type=click.Path())
@click.option("--license", "license_", default=None, type=click.Choice(["cc-by", "any"]), help=_VIDEO_LICENSE_HELP)
@click.option("--max-results", default=None, type=int)
@click.option("--page-size", default=50, show_default=True, type=int)
@click.option("--resume/--no-resume", default=True, show_default=True, help="Skip sounds already downloaded in the manifest.")
@click.option("--overwrite", is_flag=True, help="Re-download even if present.")
@click.option("--rate-delay", "rate_delay", default=0.5, show_default=True, type=float, help="Seconds between requests.")
@click.option("--fail-fast", is_flag=True, help="Stop at the first download error.")
def video_download(
    query: str | None,
    manifest_arg: str | None,
    outdir: str,
    license_: str | None,
    max_results: int | None,
    page_size: int,
    resume: bool,
    overwrite: bool,
    rate_delay: float,
    fail_fast: bool,
) -> None:
    """Download audio: from a QUERY (search term or URL), or from --manifest FILE."""
    from .core.engine import download_refs, search_all, write_search_records
    from .core.model import SearchParams

    outdir_path = Path(outdir)
    manifest = Path(manifest_arg) if manifest_arg else outdir_path / "manifest.jsonl"
    provider = _video_provider()

    if query:
        params = SearchParams(
            query=query,
            filters=_video_filters(license_),
            page_size=page_size,
            max_results=max_results,
            extra={"page": 1},
        )
        refs = search_all(provider, params)
        if not manifest_arg:
            write_search_records(manifest, refs, total=len(refs))
        click.echo(f"found {len(refs)} sounds")
    elif manifest_arg:
        refs = _refs_from_manifest(manifest)
        click.echo(f"loaded {len(refs)} sounds from {manifest}")
    else:
        raise click.UsageError("provide a QUERY or --manifest FILE")

    results = download_refs(
        provider,
        refs,
        outdir_path,
        manifest,
        resume=resume,
        overwrite=overwrite,
        fail_fast=fail_fast,
        rate_delay=rate_delay,
    )
    _report_downloads(results)


@video.command("status")
def video_status() -> None:
    """Show what's configured for the video source."""
    provider = _video_provider()
    if provider.status()["yt_dlp_installed"]:
        click.echo("yt_dlp: installed")
    else:
        click.echo('yt_dlp: missing (run `pip install "soundfetch[video]"`)')


if __name__ == "__main__":
    main()
