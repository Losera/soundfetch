# Soundfetch 0.5.0 beta-readiness record

This document tracks the readiness evidence for the 0.5.0 candidate, which
layers a breaking MCP contract change onto the 0.4.0 beta. A checked item
means the named evidence was actually produced; it does not authorize tagging
or publication.

## Supported beta claim

Unchanged from 0.4.0: the CLI and public Python API on Linux with Python 3.10
through 3.13. Python 3.14 and newer, macOS, Windows, desktop MCP hosts,
Incant Audio integration, containers, and hosted services remain experimental
or deferred.

## 1. Human semantic diff review

Completed in-session on 2026-10-17 against base commit `651b021` (merged PR
#25, the previous `main` tip):

- **PR [#26](https://github.com/Losera/soundfetch/pull/26)** — the breaking
  MCP contract change (native structured results, default-provider change,
  `report_manifest`, `provider_ids` selection, filter surface, version bump,
  CHANGELOG, CI mypy gate). Full diff presented and explicitly approved before
  commit. Merged to `main` as `061690d`.
- **PR [#27](https://github.com/Losera/soundfetch/pull/27)** — contributor
  onboarding docs and packaging metadata (no behavior change). Merged to
  `main` as `2e6b431`.
- Both merges' CI runs passed the full matrix (`test` 3.10–3.13, `package`,
  `mcp`, `export`) on `main`.

## 2. Deterministic verification

Run on `release/0.5.0` at commit `4d1a611`, Python 3.13.14 (this worktree's
`.venv`):

- `.venv/bin/python -m pytest -m "not live"`: **299 passed, 5 deselected**.
- `.venv/bin/python -m pip install -e ".[mcp]"` then
  `.venv/bin/python -m pytest tests/unit/test_mcp.py tests/unit/test_mcp_protocol.py`:
  **18 passed**.
- `.venv/bin/python -m mypy src/soundfetch/__init__.py src/soundfetch/api.py src/soundfetch/core/model.py src/soundfetch/core/provider.py src/soundfetch/mcp.py`:
  clean.
- `git diff --check`: clean.

This candidate (`release/0.5.0` at `4d1a611`) was pushed and its own CI run
(https://github.com/Losera/soundfetch/actions/runs/39089651990) passed all
seven jobs: `test` on Python 3.10, 3.11, 3.12, and 3.13, `package`, `mcp`, and
`export`.

## 3. Release candidate validation

Version `0.5.0` agrees between `pyproject.toml` and
`src/soundfetch/__init__.py`.

- `.venv/bin/python -m build` produced exactly `soundfetch-0.5.0-py3-none-any.whl`
  and `soundfetch-0.5.0.tar.gz`.
- `.venv/bin/python -m twine check dist/*`: both **PASSED**.
- Wheel SHA-256:
  `ef52c78c8aa5df81c04b19b4c9c6a3b07077db69e7eca427ad9645bad7658ad8`
- Source archive SHA-256:
  `276ba9e1539fe3a96802c41a143046fbf33ce05566685de471346dd556f3c276`

These are pre-review build artifacts, not final release files. Do not publish
them; a final candidate must rebuild from a committed, pushed, tagged commit
and record new hashes if anything changes.

## 4. Wheel-only smoke test

Fresh virtual environment, **Python 3.13.14** (a supported interpreter, not
the local default of 3.14.7):

- `soundfetch --version` → `soundfetch, version 0.5.0`.
- `soundfetch --help`, `soundfetch sources --json` (lists `archive`,
  `freesound`, `openverse`, `video`), and
  `soundfetch manifest report <empty-manifest> --json` all passed.
- `python -c 'import soundfetch, soundfetch.api, soundfetch.cli, soundfetch.core'`
  resolved `soundfetch.__file__` beneath the temporary environment, not this
  checkout.
- Installing the `mcp` and `export` extras into the same wheel environment and
  importing `soundfetch.mcp` and `soundfetch.export` both succeeded.

A separate smoke on the local default Python 3.14 (experimental, not part of
the supported claim) passed identically and is not counted as supported-version
evidence.

## 5. Authorized live smoke

Run from the Python 3.13 wheel environment above, with network access and
within this session's existing live-testing conventions (bounded
`max-results`, small files):

- **Archive**: `soundfetch archive search rain --max-results 1 --page-size 1 --json`
  returned exactly one result with provider metadata and a checksum; progress
  (`archive metadata: 1/1`) was emitted on stderr, not stdout.
- **Openverse**: `soundfetch openverse search "single bird chirp" --license cc0 --extension mp3 --max-results 2 -o .`
  returned two CC0 MP3 records with full attribution metadata;
  `soundfetch manifest report` on the resulting manifest reported two
  effective records, zero missing license/source-url gaps.
- **Selected download end-to-end** (new in 0.5.0 — the 0.4.0 trial only
  exercised search): `soundfetch openverse download --manifest ... --provider-id <id> -o .`
  downloaded exactly the one selected record (`Single_Bird_Chirp.mp3`, 9,811
  bytes); `manifest report` then showed `status_counts.downloaded=1`,
  `status_counts.listed=1` (the unselected second record untouched), and the
  manifest's append-only upgrade (`effective=2`, `superseded=1`). Repeating
  the same download call correctly skipped the already-downloaded file
  (`status: "skipped"`).

No desktop MCP host trial was repeated for 0.5.0; the existing row in
`docs/mcp-host-validation.md` (Claude Desktop 1.24012.9, unofficial Arch
Linux package, search-only) remains the only host evidence and is unchanged
by this candidate — it predates the MCP contract change, so it does not
demonstrate the new native-object results or `report_manifest` against a real
desktop host.

## Remaining blockers

1. **First-publication credential path: decided, not yet executed.** The
   maintainer chose a one-time user-scoped PyPI API token for this first
   upload, rotating to a project-scoped token immediately afterward, over a
   trusted-publisher setup (which would need its own reviewed `release.yml`
   change first). The maintainer still needs to generate that token on PyPI
   themselves — an agent cannot create account credentials — before §6 can
   run.
2. **No desktop MCP host trial exists for the new contract.** Not a blocker
   for this narrower Linux CLI/API beta claim (per the 0.4.0 precedent), but
   the MCP host validation matrix's "experimental" status is now additionally
   stale in substance: the one completed row tested the old string-encoded
   tool contract, which no longer exists.
3. **No tag exists and nothing is published.** Tagging and publication
   require explicit human authorization per `docs/RELEASE.md` §5–6, which has
   not been given.

## Release decision

**Not release-ready yet.** Item 1 is the one concrete remaining action, and
it is the maintainer's to take (PyPI does not let anyone else generate a
token on their account). Item 2 is a disclosed limitation, not a blocker,
consistent with how 0.4.0 treated desktop-host evidence. No tag or
publication is authorized by this
document.
