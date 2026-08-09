# soundfetch — review findings log

Status legend: `[open]` / `[fixed]` / `[won't fix]`. This is the triage log for
the adversarial review. Findings from the local LLM are appended here after
verification; the items below are the seed corpus verified during the initial
pass.

## P0 — correctness

### 1. `RateLimiter.acquire()` busy-spins under a non-advancing sleep — `core/pacing.py:68-87` — [fixed]
- **Evidence**: the `while True` loop refills tokens from `time.monotonic()` and
  sleeps; when `sleep` is a no-op (the documented "monkeypatch `time.sleep`"
  contract), the clock never advances, so `tokens` never reaches 1.0 and the
  loop spins indefinitely. `tests/unit/test_engine.py::test_rate_delay_sleeps_between_downloads`
  records ~2.2M `0.4998` sleeps and hangs.
- **Fix**: make `acquire()` deterministic — compute the wait, sleep once, then
  consume a token (no recheck loop), matching the documented "old `rate_delay`
  semantics" (first request free, then `1/rate` seconds between each).

## P1 — contract / test isolation

### 2. Repo `.env` leaks into CLI status — `cli.py:582-604` — [fixed]
- **Evidence**: `_load_dotenv()` reads the repo-root `.env`, so
  `test_status_reports_missing_without_env` sees `api_key: configured` despite
  deleted env vars. Running `soundfetch freesound status` from the repo root
  reports "configured" purely from `.env`. (Note: loading `.env` is documented
  behavior; the fix is test isolation, not a product change.)
- **Fix**: monkeypatch `cli._load_dotenv` to a no-op in the test (or set cwd to
  a directory without `.env`).

### 3. `status()` contract diverged from its test — `freesound/provider.py:225` — [fixed]
- **Evidence**: `status()` now returns an intentional extra key
  `oauth_token_expired`; `test_reports_missing_when_nothing_configured` asserts
  the exact old 4-key dict.
- **Fix**: update the test to include the new key; add a positive case for a
  cached-but-expired token (`{"oauth_token": False, "oauth_token_expired": True}`).

### 4. `adapters/__init__.py` docstring claims a tool that doesn't exist — [fixed]
- **Evidence**: docstring mentions 5 tools incl. `export_dataset` and a
  `get_tools()` entry point; only 4 tools exist and the real entry points are
  `langchain_tools()` / `llamaindex_tools()` / `smolagents_tools()` / `build_tools()`.
- **Fix**: correct the docstring (4 tools, real names).

## P2 — coverage gaps / incomplete features

### 5. Zero test coverage for new surface — [fixed]
- `core/pacing.py`, `mcp.py`, `export.py`, `adapters/*`, and the threaded
  `workers>1` download path have no unit tests.

### 6. New pacing machinery unreachable from the CLI — [fixed]
- `_run_search`/`_run_download` pass no `pacing`; the CLI only exposes the legacy
  `--rate-delay`. `--workers` and `--rate` should be exposed on `download`.
