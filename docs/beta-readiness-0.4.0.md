# Soundfetch 0.4.0 beta-readiness record

This document tracks the five concrete readiness actions from the August 2026
public-beta review. A checked automated item means the named evidence was
actually produced; it does not authorize tagging or publication.

## 1. MCP host readiness

- [x] Unit and subprocess protocol coverage exists in CI.
- [x] Complete and record the manual Claude Desktop trial below (scoped to one
      unofficial Linux packaging — see caveats in the table).

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
| Date / tester | 2026-08-11, Juan Naranjo |
| OS / Claude Desktop | Claude Desktop 1.24012.9, Arch Linux (rolling, x86_64), kernel 7.1.4-arch1-1. **Not an officially supported platform**: Anthropic's Linux Desktop beta (launched 2026-06-30) officially supports only Ubuntu 22.04+/Debian 12+ via apt; this run used the `claude-desktop` AUR package (v1.24012.9-1), an unofficial repackaging of the same upstream `.deb` — unsigned (`Validated By: None`), built locally from a PKGBUILD. See sources below. |
| Commit / wheel / SHA-256 | `b1ace99bffe3ce2b553244100010045c739e47fb` / `soundfetch-0.4.0-py3-none-any.whl` / `7960914a429d41dcdafa6773141444a57b83e0990fec33fe9d8d8816a0e4534f` |
| Tool discovery | Pass — all 4 tools (`list_sources`, `check_provider_status`, `search_sounds`, `download_manifest`) resolved with full parameter schemas. |
| Provider status | Pass — `check_provider_status("archive")` → `{"ok": true, ...}`, no auth required. |
| Bounded search | Pass — `search_sounds(archive, "rain", max_results=1)` returned exactly 1 result as clean structured JSON; no log/progress bleed into the payload. |
| Shutdown and cleanup | Not verified — not exercised or reported in this run. |

**Scope caveats:**
- Tested on unofficial Arch/AUR packaging only. macOS, Windows, and the
  officially supported Linux distros (Ubuntu/Debian) remain untested.
- `download_manifest` was **not** called in this trial (the prompt
  intentionally skips downloads) — the stdio path most likely to break under
  a real host (progress output corrupting the JSON stream) is still untested
  through Claude Desktop specifically. It was separately verified through
  soundfetch's own MCP tools directly (not through Desktop) — see
  `docs/deferred-work.md`.
- "No unexpected files created" was not independently confirmed — absence of
  a written-path reference in the three responses, not a filesystem check.

**Findings surfaced by this trial (not blocking, filed as issues — both now
resolved, see below):**
- [#13](https://github.com/Losera/soundfetch/issues/13) — Archive
  `download_url` values contain raw unencoded spaces (e.g. `.../For Now
  (Loz Goddard_s Rain In Space Mix).m4a`); a naive HTTP client could fail or
  mangle the request. **Fixed** in `991ce3b` (percent-encodes the filename
  segment); closed 2026-08-12.
- [#14](https://github.com/Losera/soundfetch/issues/14) — Archive-provider
  relevance for simple queries is weak: `rain` returned a house-remix track
  whose title merely contains the word "Rain," not an actual rain-sound
  recording. Protocol behavior is correct; result quality may surprise
  first-time testers. **Documented** (not changed) in `991ce3b` — this is IA's
  own relevance ranking over its full audio catalog, not a soundfetch defect;
  the docstring/README now point callers wanting effect-like results at
  `tag`/`raw` filters instead of bare keywords. Closed 2026-08-12.

Sources: [Anthropic releases Claude Desktop app beta for Linux users](https://cryptobriefing.com/anthropic-claude-desktop-linux-beta/), [Claude Desktop for Linux: Anthropic Launches the Official Beta](https://basic-tutorials.com/news/claude-desktop-for-linux-anthropic-launches-the-official-beta/)

**Supplementary non-Desktop smoke test (does not satisfy the gate above).**
On 2026-08-11, the three bounded calls (`list_sources`, `check_provider_status`
for `archive`, `search_sounds` for `archive`/`rain`/`max_results=1`) were run
against commit `b1ace99` / wheel `soundfetch-0.4.0-py3-none-any.whl` (sha256
`7960914a...e4534f`) in a Cowork sandbox, not Claude Desktop. All three
succeeded with clean structured JSON, no stderr/log bleed into the payload,
`max_results` respected, and no files written. Host shutdown was not
exercised. This confirms the MCP server itself behaves correctly but does not
substitute for the Desktop trial: no Desktop version/OS was recorded, and the
client was a different MCP host implementation than the one being advertised
as compatible.

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

The first like-for-like 0.4.0 attempt, `benchmarks/review-20260811-0.4.0-evidence/`,
produced no valid sample (missing `FREESOUND_API_KEY`; no Archive candidate
under the 1 MB cap in that run) and is retained as failure evidence, not a
performance result.

**A second attempt on 2026-08-12, `benchmarks/review-20260812-0.4.0-evidence/`,
used the identical bounded command (same query, caps, trials, and worker
counts) and produced a full 12/12 valid sample** — 6 Freesound and 6 Archive
configurations, zero failures. (The Archive discovery gap in the first attempt
appears to have been day-to-day catalog/ranking variance from IA's own
relevance scoring — consistent with the #14 finding — rather than a structural
problem with the cap; no cap was relaxed to obtain this result.)

Average throughput vs. the 0.3.0 baseline: Freesound 0.0986 → 0.1038 MB/s
(+5.3%), Archive 0.2148 → 0.2052 MB/s (−4.5%). Both files involved are small
(≈180 KB and ≈377 KB) and each configuration is a single-file, network-bound
sample, so these deltas are within measurement noise — **no regression or
improvement claim is made**. This closes the evidence gap (a valid sample now
exists); it does not certify performance parity.

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

## Remaining blockers

As of 2026-08-12, with PR #15 merged to `main` (`052ce74`), what still stands
between this candidate and a beta claim:

1. **Human semantic diff review** (item 1 of `docs/RELEASE.md` §5) has not
   happened. This is the hard blocker; nothing else in this document
   substitutes for it. During that review a real correctness bug was found and
   fixed in PR #17 (not yet merged as of this writing): `api.download()`
   silently reordered results relative to the input refs whenever a manifest
   interleaved more than one provider, which corrupted the new
   `download --json` contract's per-item `provider_id`/`status`/`checksum`
   attribution — the exact feature the release notes market as stable for
   external consumers. This is itself evidence for why the review step exists
   and cannot be skipped or assumed satisfied by test counts alone.
2. **MCP host trial (item 1 of the checklist) is recorded but narrower than a
   beta claim needs**: unofficial Arch/AUR packaging only (macOS, Windows, and
   the officially supported Ubuntu/Debian builds are untested); host shutdown/
   cleanup was not exercised in the original recorded trial; `download_manifest`
   has never been called through Claude Desktop itself (only through
   soundfetch's own MCP client directly — see `docs/deferred-work.md`). A
   follow-up trial exercising both gaps against the current (post-fix) wheel
   is in progress as of this writing.
3. **No tag exists and nothing is published.** Tagging and publication require
   explicit human authorization per `docs/RELEASE.md` §5–6, which has not been
   given.

Items 2 (deterministic verification), 3 (release candidate validation), 4
(Archive usability), and 5 (reproducible benchmark evidence, updated above) of
the original five-point checklist are now satisfied. Item 1 (MCP host
readiness) remains the only checklist item with open gaps, per point 2 above.

## Release decision

**Not release-ready yet.** Human semantic diff review remains mandatory — and,
per the note in "Remaining blockers" above, that review already earned its
keep by catching a real silent-corruption bug (PR #17) in the candidate's
headline JSON contract feature, which a passing test suite alone did not
surface. The manual Claude Desktop trial is now recorded, but scoped to one
unofficial Linux packaging (Arch/AUR) with shutdown and `download_manifest`
gaps still open — if the 0.4.0 beta claim is meant to cover macOS/Windows/
official-Linux users, or a Docker-packaged distribution, those remain untested
and are separate open items, not implied by this record. The benchmark
evidence gap is closed as of 2026-08-12. Any failed deterministic/package check
adds a new gate; no tag or publication is authorized by this document.
