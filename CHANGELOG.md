# Changelog

Soundfetch follows semantic versioning for its public CLI, Python API, manifest,
and machine-readable tool contracts.

## Unreleased

## 0.5.0.dev0

### Breaking

- MCP tools return native structured objects instead of JSON-encoded strings.
  Clients that called `json.loads()` on a tool result must stop doing so.
- `search_sounds` and `check_provider_status` default to credential-free
  Openverse instead of Freesound. Pass `provider="freesound"` explicitly to
  keep the previous default behavior.

### Added

- `report_manifest` exposes read-only dataset health to MCP clients.
- `download_manifest` accepts reviewed provider IDs for selected downloads.
- `search_sounds` exposes the shared license, duration, tag, category,
  source, extension, length, generative-AI preference, and sort filters.

### Changed

- `search_sounds` returns a concise, selection-oriented result by default;
  pass `include_metadata=true` for the complete provider metadata mapping.

## 0.4.0 - 2026-09-01

- First tagged public-beta candidate with Openverse, Freesound, Internet
  Archive, and optional video providers.
- Added append-only manifest reporting, resumable downloads, structured CLI
  output, Python and MCP interfaces, attribution export, and WebDataset export.
