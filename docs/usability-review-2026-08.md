# Soundfetch public-beta usability review

Date: 2026-08-09 (America/New_York)

## Executive finding

Soundfetch is useful today for a technically comfortable person running it
from a source checkout. Its strongest design is the two-phase workflow: search
into an append-only manifest, inspect that durable index, then download with
resume and per-item checkpoints. The CLI and Python API both completed live
Freesound and Internet Archive collections in this review.

The staged candidate is technically ready for a human-reviewed public beta:
distribution metadata, license, package checks, CI, and an MCP protocol test
are present. It is not yet released or tagged, the agent work remains unmerged,
and Internet Archive search is slow for even small batches. Publication still
requires semantic review and the normal release process.

No prior benchmark result files survived. Earlier commits added benchmark
scripts and claimed 189/190 offline tests, but they did not retain CSV, JSON,
charts, or console output. All performance values below are new measurements,
not reconstructed historical results.

## Measurements

The retained raw evidence is in
[`benchmarks/review-20260809-small/`](../benchmarks/review-20260809-small/).
The run used Python 3.14.6 on Linux, query `rain`, three trials per
configuration, the first two eligible files per source, a 1 MB per-file cap,
and a 100 MB total cap. Twenty-four file downloads completed without recorded
errors. These are exploratory network measurements, not provider-wide service
level claims.

| Source / workers | Search mean | Download mean | Effective MB/s | Per-file p50 | Per-file p95 | Parallel speedup |
|---|---:|---:|---:|---:|---:|---:|
| Freesound / 1 | 1.381 s | 3.601 s | 0.107 | 1.718 s | 2.313 s | baseline |
| Freesound / 4 | 1.365 s | 2.630 s | 0.147 | 2.194 s | 2.660 s | 1.37× |
| Archive / 1 | 40.521 s | 2.690 s | 0.209 | 1.301 s | 1.574 s | baseline |
| Archive / 4 | 40.781 s | 1.496 s | 0.376 | 1.405 s | 1.553 s | 1.80× |

The charts show the relationship more clearly:

- [Effective throughput](../benchmarks/review-20260809-small/throughput.png)
- [Per-file latency](../benchmarks/review-20260809-small/latency.png)
- [Mean completion time](../benchmarks/review-20260809-small/completion-time.png)

The black-box CLI trial independently downloaded two files per provider.
Freesound search took 1.682 seconds and its download command took 4.282
seconds; Archive search took 40.666 seconds and download took 2.791 seconds.
Both search commands emitted parseable JSON and both manifests produced the
expected number of completed files.

Four workers reduce end-to-end download time, but the sample is too small to
justify four workers as a universal default. The higher concurrent Freesound
per-file latency also shows why wall-clock completion and per-file latency must
both be reported. Archive's dominant cost is search: each result requires an
additional metadata request to resolve a concrete audio file, so adding
download workers cannot fix its roughly 40-second discovery stage.

## How a person uses Soundfetch

The clearest human workflow is:

1. Install from a checkout and run `soundfetch sources` and provider `status`.
2. Search without downloading, preferably with license and Freesound
   `gen_ai_preference` filters.
3. Inspect `manifest.jsonl` as JSONL or a pandas dataframe.
4. Remove or reject unsuitable records outside Soundfetch, then download the
   reviewed manifest.
5. Re-run the download command to resume; use the manifest as the dataset
   index and audit trail.

This is usable for Python developers, ML/audio researchers, and technical
archivists who understand credentials, licenses, and command-line tools. The
README provides runnable examples, Archive needs no credentials, errors are
generally actionable, and the JSON mode makes scripting practical.

The main human barriers are source-only installation, no release/version
history, no CI evidence on the public default branch, provider-specific filter
semantics that can be silently ignored by the shared API, slow Archive search,
and no interactive review UI. License filtering helps collection but does not
replace a human legal/compliance review.

## How an agent would use Soundfetch

The intended agent workflow is deliberately narrower:

1. Call `list_sources` and `check_provider_status`.
2. Call `search_sounds` with a bounded result count and explicit license,
   tag/duration, and generative-AI preferences.
3. Review compact result fields, then save a manifest.
4. Call `download_manifest` in a user-approved directory with conservative
   worker/rate controls.
5. Treat any partial failure as failure and inspect the bounded error list.

The staged MCP implementation now has compact structured results, validates
limits before side effects, preserves Freesound compliance metadata, and does
not report partial success as `ok: true`. Its plain tool functions and schema
registration are covered by deterministic tests.

The initial MCP 1.29.0 and 2.0.0 initialization attempts timed out because the
restricted review sandbox prevented AnyIO worker threads from running. MCP's
stdio server reads stdin through that worker-thread path, so an empty SDK server
failed identically. Outside that restriction, real subprocess handshakes passed
on Python 3.13.14 and 3.14.6: the client initialized, listed all four tools, and
called `list_sources` with structured content. The same exchange is retained as
an end-to-end CI test, so stdio behavior is verified rather than inferred from
tool-registration unit tests.

## Will people or agents use it?

There is a real niche: collecting licensed sound effects and field recordings
for ML, games, research, and creative work is tedious, and Soundfetch's shared
manifest/resume model is more reproducible than one-off provider scripts.
People are likely to use it if installation becomes routine and the README is
discoverable through a package release. The public repository currently shows
only two stars, no forks, and no release packages, so there is not yet evidence
of meaningful adoption.

Agents could benefit because the work is naturally tool-shaped and produces a
machine-readable checkpoint. They will not use the current public branch in
practice because there is no released MCP extra or registry entry. MCP is still
the right minimal direction because it is host-neutral; maintaining three
framework-specific adapters before there is usage evidence would create more
compatibility surface than value.

## Readiness actions

Before calling version 0.3.0 a public beta:

1. Keep the end-to-end MCP subprocess test in CI and perform a named desktop or
   agent-host trial before advertising compatibility with that host.
2. Keep the downloader checksum/resume fix, JSON CLI, input validation,
   timing, pacing, and worker controls together and run the complete offline
   suite on every supported Python version.
3. Build and install wheel and source distributions, run `twine check`, add the
   MIT license/project metadata, tag the release, and publish only after a
   human semantic review.
4. Optimize Archive metadata resolution or expose its progress so a 40-second
   ten-result search does not look hung.
5. Retain benchmark raw metrics and environment metadata for future runs;
   compare identical bounded samples before claiming regressions or gains.
6. Defer framework adapters and dataset exporters until users request them and
   their real optional dependencies can be tested.

References: [public repository](https://github.com/Losera/soundfetch),
[official MCP Python SDK](https://py.sdk.modelcontextprotocol.io/), and
[official MCP Registry](https://registry.modelcontextprotocol.io/).
