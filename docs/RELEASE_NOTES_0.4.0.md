# Soundfetch 0.4.0 beta release notes

Soundfetch 0.4.0 is the first planned public beta of the multi-provider audio
collection CLI and Python library. Publication remains gated on human semantic
review and the checks in `docs/RELEASE.md`.

## Highlights

- Search and download from Freesound and Internet Archive through one
  append-only, last-record-wins manifest format; the optional video provider
  uses `yt-dlp`.
- Resume-safe downloads, checksum validation, bounded worker pools, rate
  controls, structured JSON CLI output, and provider metadata progress.
- A public Python API for search, manifest review, selected downloads, and
  mixed-provider collections.
- Four MCP tools for source discovery, provider status, bounded search, and
  manifest downloads.
- Optional WebDataset and attribution exports with real-dependency CI coverage.
- Repeatable `--provider-id` selection and stable JSON results for native
  consumers. Incant Audio compatibility has not yet been verified end to end.

## Supported beta scope

- Release-tested: Linux with Python 3.10 through 3.13, using the CLI and public
  Python API.
- Experimental: MCP desktop hosts, Python 3.14 and newer, macOS, Windows, and
  downstream Incant Audio integration.
- Not included: a hosted service, container image, availability guarantee, or
  provider service-level guarantee.

## Known limitations

- Freesound searches require an API key; original files additionally require
  OAuth2.
- Internet Archive search resolves file metadata per item and can take tens of
  seconds even for a small result page. Progress is emitted on stderr.
- Claude Desktop registration is documented, but desktop-host operation is
  experimental. The recorded trial did not exercise host-driven downloads or
  shutdown/cleanup.
- The framework-specific adapters and broken Hugging Face dataset exporter are
  deliberately deferred; see `docs/deferred-work.md`.
- Live benchmark results are network- and catalog-dependent and are not service
  level claims.

## Release status

There is no tag or published package for 0.4.0. Build artifacts produced during
readiness review are candidates only and must not be published before the human
release gate.
