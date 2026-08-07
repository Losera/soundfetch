# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`soundfetch` — a CLI that batch-searches sound databases, downloads audio
(previews or lossless originals), and writes a machine-readable JSONL
manifest of every sound it finds. Freesound and Internet Archive are the
implemented sources; the codebase is architected so additional sources
(e.g. video) plug in without touching core code. See `README.md` for
user-facing usage and `PLAN.md` for the full design rationale and phased
rollout — note `PLAN.md` itself is corrupted (a bad wrapped-terminal paste
dropped characters at nearly every line break), so treat it as a rough
guide, not a literal spec; cross-check anything load-bearing against the
actual code.

`freesound_download.py` at the repo root is the old, broken pre-rewrite
script (hardcoded path to another machine, wrong API usage, wav-labeled
mp3s). It is dead code kept for reference only — do not build on it or fix
it; extend `src/soundfetch/` instead.

## Commands

```bash
# Install (editable)
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

# Run the CLI
soundfetch sources
soundfetch freesound search "piano" --license cc0 -o out/
soundfetch freesound download "piano" --mode preview -o out/
soundfetch freesound status
soundfetch archive search "rain storm" --license cc0 -o out/
soundfetch archive download --manifest out/manifest.jsonl -o out/
soundfetch archive status

# Tests
pytest -m "not live"   # offline suite, no API key/network needed (default via addopts)
pytest -m live         # live smoke tests against the real Freesound + Internet Archive APIs
pytest path/to/test_x.py::test_name   # single test
```

`tests/` follows the layout `PLAN.md` describes: `conftest.py` (shared
fixtures) + `fakes.py` (`FakeProvider`, a scripted `Provider` test double)
at the top level, `unit/` (one file per `core/*` module, one per provider,
plus `test_cli.py` using `click.testing.CliRunner`), and `live/` (real
network smoke tests, gated behind the `live` marker so they never run by
default). `tests/` and `tests/unit/` are real packages (have `__init__.py`)
so test modules can `from ..fakes import FakeProvider, make_ref`. The
Freesound live tests additionally `skipif` when `FREESOUND_API_KEY` isn't
set; the Internet Archive ones need no key so they always run under
`-m live`, they're just kept out of the default offline suite because they
still hit the real network. When adding a provider or core module, add its
test file in this layout rather than inventing a new one.

Config: copy `.env.example` to `.env` (`FREESOUND_API_KEY`, and
`FREESOUND_CLIENT_ID`/`FREESOUND_CLIENT_SECRET` for OAuth2 originals).
`soundfetch` loads `.env` via `python-dotenv`; precedence is CLI flag > env
var > `.env`.

## Architecture

The core/provider split is the load-bearing design decision — read
`core/provider.py`'s docstring before touching anything.

- **`core/model.py`** — provider-agnostic dataclasses (`SearchParams`,
  `SoundRef`, `SearchPage`, `DownloadResult`). This is the contract
  between providers and the core engine; providers map their API
  responses onto these, and core never sees provider-specific payloads.
- **`core/provider.py`** — the `Provider` Protocol (`search()` /
  `download()`) plus a lazy `REGISTRY: dict[name -> "module:ClassName"]`
  resolved via `importlib`, so importing core never pulls in a provider's
  dependencies. Adding a source = one new module implementing the
  Protocol + one registry line.
- **`core/engine.py`** — `search_all()` (pagination loop, calling
  `provider.search()` page by page via `SearchParams.extra["page"]`) and
  `download_refs()` (the download loop: resume-skip already-downloaded
  sounds, per-run+on-disk filename collision handling via `names.py`,
  rate-delay between requests, manifest checkpointing after every single
  attempt). Providers never implement pagination or resume — that logic
  lives here once, for every source.
- **`core/manifest.py`** — the append-only `manifest.jsonl` reader/writer.
  One JSON object per line; the effective record for a sound is the
  **last line** with a given `(provider, provider_id)` — so re-searching
  or re-downloading never rewrites the file, it just appends. This one
  artifact serves as search output, download checkpoint, resume log, and
  dataset index (consumed via `pd.read_json(..., lines=True)`).
  `latest_by_sound()` / `iter_latest()` do the last-wins dedup.
- **`core/downloader.py`** — `stream_to_file()`: streams to a
  `<dest>.part` file, resumes via HTTP `Range` if a partial file exists,
  verifies an optional md5 checksum, then atomically `os.replace()`s into
  place. Used by every provider's download path — this is the piece that
  makes resume/checkpointing work at the byte level, distinct from
  engine.py's resume at the manifest level.
- **`core/net.py`** — `retry()` / `get_json()`: shared HTTP retry with
  `Retry-After` honoring on 429 plus exponential backoff+jitter on
  5xx/connection errors. `HttpError`/`RateLimitError` carry the parsed
  server error body.
- **`core/names.py`** — filename sanitization
  (`[A-Za-z0-9._-]`, 120-char cap) and `unique_path()` collision
  avoidance (`name (1).ext`, `name (2).ext`, ...), checked against both
  files already on disk and names already claimed earlier in the same run.
- **`providers/freesound/`** — `provider.py` does direct Freesound API v2
  calls (deliberately *not* the `freesound-python` SDK — see its module
  docstring for why: the SDK's `Pager` only fetched one page and its
  download methods can't do `.part` resume or expose `Retry-After`).
  `filters.py` translates provider-agnostic filters (`license`,
  `duration`, `tag`, `gen_ai`) into Freesound's Solr `filter` query syntax
  — the `LICENSES` dict there is the single source of truth for
  license-code → Freesound-string mapping, confirmed against live API
  responses. `auth.py` implements the OAuth2 authorization-code flow
  (spins up a localhost callback server, caches tokens with auto-refresh
  at `$SOUNDFETCH_CONFIG_DIR/freesound.json`, mode 0600) — required only
  for `--mode original` (lossless) downloads; a plain API key only ever
  gets low-quality previews.
- **`providers/archive/`** — Internet Archive, no auth (IA serves
  original-quality files to anyone). The one architectural wrinkle versus
  Freesound: an IA search hit ("item") is a bundle of files, not a single
  sound, so a query result alone doesn't say which file to download. Since
  `core/engine.py` needs `SoundRef.file_format` before it ever calls
  `download()` (for naming/collision handling), `provider.py` resolves one
  representative audio file per item *during `search()` itself* — an
  extra `GET /metadata/<id>` call per hit, preferring the item's original
  upload over IA-generated derivatives, then the best available extension
  (`AUDIO_EXTENSIONS` priority order). This is the one provider where
  search does more than one HTTP call per page. `filters.py` always ANDs
  `mediatype:(audio)` and `NOT access-restricted-item:true` into the query
  — the latter excludes IA's lending/streaming-only items, whose files
  404/401 on direct download and are useless to a batch downloader; license
  codes map to `licenseurl` wildcard patterns (IA has no license enum) and
  `tag` maps to IA's `subject` field.
- **`cli.py`** — click group wiring (`soundfetch <provider> <verb>`).
  Keeps provider imports inside command functions (not at module level)
  so `soundfetch --help` doesn't pay the cost of importing every
  provider's dependencies. `_refs_from_manifest()` and
  `_report_downloads()` are provider-agnostic and shared by every
  provider's `download` command — the manifest record shape coming out of
  `core/engine.py` is identical regardless of source.

### Design decisions worth knowing before changing things

- Search/download flows go through `core/engine.py`, never call a
  provider's `search`/`download` directly from `cli.py`, to keep
  pagination/resume/checkpointing centralized.
- The manifest is the checkpoint. There's no separate resume-state file —
  `download_refs(resume=True)` reads the manifest and skips sounds whose
  latest record has `status: "downloaded"` and the local file still
  exists on disk.
- `gen_ai_preference` is always recorded in the manifest metadata (never
  silently dropped) because it's load-bearing for ML-training license
  compliance, one of this tool's primary use cases.
- New providers should raise/propagate `core.downloader.DownloadError`
  (or subclasses like `ChecksumMismatch`) on unrecoverable download
  failures — `engine.download_refs()` specifically catches that type to
  record `status: "error"` in the manifest, append an `error`-status
  `DownloadResult` to its return list (so `cli._report_downloads()` can
  see the failure and set a nonzero exit code), and continue (or stop,
  under `--fail-fast`).
- `engine.ref_record()` is the single place that turns a `SoundRef` into
  a manifest envelope, and every provider's `search()` returns `SoundRef`
  — this is *why* `soundfetch freesound search` and `soundfetch archive
  search` produce schema-identical manifests without either provider
  knowing about the other. Don't build provider-specific manifest fields
  outside of `SoundRef.metadata`.
