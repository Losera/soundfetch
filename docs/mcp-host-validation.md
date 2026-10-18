# MCP host validation

MCP compatibility is an evidence claim, not an assumption. A host is marked
verified only after testing the installed Soundfetch wheel and recording the
host version, operating system, Soundfetch version, and artifact hash.

| Host | Platform | Search | Report | Selected download | Resume | Shutdown | Status |
|---|---|---:|---:|---:|---:|---:|---|
| Claude Desktop 1.24012.9 | unofficial Arch Linux package | yes | not tested | not tested | not tested | not tested | experimental |
| Claude Desktop | supported Ubuntu/Debian package | — | — | — | — | — | unverified |
| Cursor | — | — | — | — | — | — | unverified |
| Codex | — | — | — | — | — | — | unverified |

## Required trial

1. Install `soundfetch[mcp]` from the candidate wheel in a fresh environment.
2. Configure the absolute `soundfetch` executable and a dedicated
   `SOUNDFETCH_MCP_ROOT`.
3. Discover all five tools and confirm their schemas.
4. Call `list_sources` and `check_provider_status` without filesystem changes.
5. Search Openverse with `max_results=2`, save a manifest, and confirm the
   response is a native structured object rather than encoded JSON text.
6. Call `report_manifest`, select one small result by provider ID, call
   `download_manifest`, and report the manifest again.
7. Repeat the download and confirm it is skipped.
8. Confirm all writes remain within the configured root, stdout contains no
   protocol noise, and remote descriptions are bounded.
9. Stop the host and confirm Soundfetch exits without an orphan process.

Record failures as evidence. Do not convert an incomplete row to “verified.”
