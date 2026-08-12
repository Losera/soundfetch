# Soundfetch 0.4.0 beta-readiness record

This document tracks the five concrete readiness actions from the August 2026
public-beta review. A checked automated item means the named evidence was
actually produced; it does not authorize tagging or publication.

## 1. MCP host readiness

- [x] Unit and subprocess protocol coverage exists in CI.
- [ ] Complete and record the manual Claude Desktop trial below.

The copy-ready host prompt is in `docs/claude-desktop-trial-prompt.md`.

Manual trial procedure:

1. Install the reviewed 0.4.0 wheel with its `mcp` extra in a fresh environment.
2. Record the operating system, Claude Desktop version, Git commit, wheel
   filename, and wheel SHA-256.
3. Configure Claude Desktop to launch that environment's `soundfetch mcp`, then
   restart the host.
4. Invoke `list_sources`, `check_provider_status` for Archive, and a bounded
   Archive `search_sounds` call with query `rain` and limit `1`.
5. Record whether tool discovery, structured results, stderr handling, and host
   shutdown all behaved correctly. Remove the temporary host configuration.

| Field | Result |
|---|---|
| Date / tester | Pending |
| OS / Claude Desktop | Pending |
| Commit / wheel / SHA-256 | Pending |
| Tool discovery | Pending |
| Provider status | Pending |
| Bounded search | Pending |
| Shutdown and cleanup | Pending |

## 2. Deterministic verification

The candidate passed the full offline suite with the real MCP, export, and
benchmark extras installed. Exact local commands and results are recorded in
the verification section; GitHub Actions on merged `main` remains supporting
historical evidence only.

## 3. Release candidate validation

Version `0.4.0` must agree between `pyproject.toml` and
`src/soundfetch/__init__.py`. The candidate wheel and source distribution must
pass Twine validation, and a fresh wheel-only environment must pass version,
help, sources JSON, and base-import smoke checks. Tagging and publication remain
outside this change and require explicit human authorization.

All automated candidate checks above passed. The wheel SHA-256 is
`7960914a429d41dcdafa6773141444a57b83e0990fec33fe9d8d8816a0e4534f`;
the source archive SHA-256 is
`1f3bc5ba9ea1b630a811b6a75c24ba42be066b470a2015066f85843496233726`.

## 4. Archive usability

Archive metadata resolution reports ordered `completed/total` progress to
stderr, including when stdout is JSON. Unit and CLI regression coverage verify
the callback propagation and output separation. A bounded installed-wheel live
search is recorded separately from deterministic checks.

## 5. Reproducible benchmark evidence

The retained 0.3.0 baseline is in
`benchmarks/review-20260809-0.3.0-baseline/`. It used query `rain`, ten
candidates, three trials, worker counts 1 and 4, a 1 MB per-file cap, and a
100 MB total cap.

The like-for-like 0.4.0 attempt is in
`benchmarks/review-20260811-0.4.0-evidence/`. It retained environment and failure
metadata but produced no valid performance sample:

- all six Freesound configurations stopped because `FREESOUND_API_KEY` was not
  configured;
- all six Archive configurations completed discovery but found no candidate in
  the first ten results whose advertised download size passed the 1 MB cap.

These are failed benchmark configurations, not performance results. No
regression or improvement claim can be made. Re-run the identical bounded
command with a Freesound key and an eligible Archive sample before release if a
current performance comparison is required; do not relax the safety caps merely
to obtain favorable numbers.

## Verification record

- `.venv/bin/python -m pytest tests/unit/test_benchmark_api.py -q`:
  9 passed.
- Targeted CLI, Archive, API, and engine tests: 86 passed.
- MCP and export tests in the restricted sandbox: 19 passed and the stdio
  protocol test timed out in the known AnyIO subprocess restriction.
- The exact stdio protocol test rerun outside that restriction: 1 passed.
- `.venv/bin/python -m pytest -m "not live" -q` outside the subprocess
  restriction: 220 passed, 4 live tests deselected.
- `.venv/bin/python -m build`: produced exactly
  `soundfetch-0.4.0-py3-none-any.whl` and `soundfetch-0.4.0.tar.gz`.
- `.venv/bin/python -m twine check dist/*`: both artifacts passed.
- Fresh wheel-only environment: `--version`, `--help`, `sources --json`, and
  base imports passed; `soundfetch.__file__` resolved beneath the temporary
  environment rather than the checkout.
- Bounded installed-wheel Archive search (`rain`, maximum/page size 1): passed
  with structured JSON containing one result and metadata progress on stderr.
- `git diff --check`: passed.
- Like-for-like live benchmark: ran within the agreed caps but all 12
  configurations failed for the documented credential/eligibility reasons; it
  is retained as failure evidence, not reported as a passing benchmark.

## Release decision

**Not release-ready yet.** The manual Claude Desktop trial and human semantic
diff review remain mandatory. Any failed deterministic/package check adds a new
gate; no tag or publication is authorized by this document.
