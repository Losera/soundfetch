# Soundfetch 0.5.0 beta release notes

Soundfetch 0.5.0 is the second public-beta candidate, built on the 0.4.0
candidate's Openverse, Freesound, Internet Archive, and video providers.
Publication remains gated on human semantic review and the checks in
`docs/RELEASE.md`.

## Highlights

- **Breaking MCP contract change:** MCP tools now return native structured
  objects instead of `json.dumps()`-encoded strings. Clients that called
  `json.loads()` on a tool result must stop doing so.
- **Breaking MCP default change:** `search_sounds` and `check_provider_status`
  default to credential-free Openverse instead of Freesound. Pass
  `provider="freesound"` explicitly to keep the previous default behavior.
- A new `report_manifest` MCP tool exposes read-only dataset health
  (status, provider/license counts, bytes, duration coverage, missing
  files/checksums) without writing anything — the same report the
  `soundfetch manifest report` CLI command produces.
- `download_manifest` accepts reviewed `provider_ids` for selected downloads,
  in manifest order, matching the CLI's `--provider-id` flag.
- `search_sounds` exposes the shared license, duration, tag, category,
  source, extension, length, generative-AI preference, and sort filters, and
  returns a concise, selection-oriented result by default (`include_metadata`
  for the complete provider metadata mapping).
- CI gained a `mypy` type-check gate on the public-API surface (`__init__`,
  `api`, `core.model`, `core.provider`, `mcp`).
- New contributor-facing material: `CONTRIBUTING.md`, `SECURITY.md`, GitHub
  issue templates, an MCP host validation matrix
  (`docs/mcp-host-validation.md`), and a music-production DAW handoff
  workflow doc (`docs/music-production-workflow.md`) that states what
  Soundfetch does not do (auditioning, waveform display, BPM/key detection,
  DSP).

## Supported beta scope

- Release-tested: Linux with Python 3.10 through 3.13, using the CLI and
  public Python API.
- Experimental: MCP desktop hosts, Python 3.14 and newer, macOS, Windows, and
  downstream Incant Audio integration.
- Not included: a hosted service, container image, availability guarantee, or
  provider service-level guarantee.

## Known limitations

Carried forward from 0.4.0 (see `docs/RELEASE_NOTES_0.4.0.md` for the original
record):

- Freesound searches require an API key; original files additionally require
  OAuth2.
- Internet Archive search resolves file metadata per item and can take tens
  of seconds even for a small result page. Progress is emitted on stderr.
- Openverse anonymously limits API usage and downloads files from changing
  third-party hosts; users must verify the original landing page and license.
  Category metadata is sparse for some upstream sources, so restrictive
  category filters can return no results.
- Claude Desktop registration is documented, but desktop-host operation is
  experimental. The recorded 0.4.0 trial did not exercise host-driven
  downloads or shutdown/cleanup; no new desktop-host trial was run for 0.5.0.
- The framework-specific adapters and broken Hugging Face dataset exporter
  are deliberately deferred; see `docs/deferred-work.md`.
- Live benchmark results are network- and catalog-dependent and are not
  service level claims.
- Nothing has been published to a package index as of this candidate; see
  `docs/beta-readiness-0.5.0.md` for the exact remaining release gates.

## Release status

There is no tag or published package for 0.5.0. Build artifacts produced
during readiness review are candidates only and must not be published before
the human release gate.
