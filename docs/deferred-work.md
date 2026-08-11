# Deferred adapter and export work

The framework adapters developed for the 0.3.0 beta, and the `to_hf_dataset`
exporter specifically, are deliberately deferred. `export_attribution` and
`to_webdataset` were restored after real-dependency verification found they
work correctly; see below for why `to_hf_dataset` did not.

## Deferred files

The following are preserved at `feat/agent-usability` commit `0c4a9b3`:

- `src/soundfetch/adapters/__init__.py`
- `src/soundfetch/adapters/langchain.py`
- `src/soundfetch/adapters/llamaindex.py`
- `src/soundfetch/adapters/smolagents.py`
- `tests/unit/test_adapters.py`
- `src/soundfetch/export.py`'s `to_hf_dataset` function (the current
  `export.py` on `main` keeps `export_attribution` and `to_webdataset`)

The corresponding optional dependency groups (`langchain`, `llamaindex`,
`smolagents`, `agents`, and the `datasets[audio]` pin previously bundled into
`export`) were removed from the 0.3.0 release surface. They can be
reconstructed from commit `0c4a9b3`'s `pyproject.toml`, `README.md`, and
`llms.txt` without merging the commit wholesale.

## Why the adapters are excluded from 0.3.0

The adapters commit the project to three distinct optional framework
contracts: LangChain, LlamaIndex, and Smolagents. All three are strictly
redundant with the MCP server already shipping — it exposes the same four
tools generically to any MCP-compatible host. There is no concrete usage
evidence for any specific framework, no named maintenance owner, and their
tests are `importorskip`-gated with no CI job installing the real
dependencies, so none of the three has ever actually run.

## Why `to_hf_dataset` is excluded from 0.3.0

Unlike the adapters, this isn't a "maybe someday" deferral — the function is
currently broken. Run against the real `datasets` library with a minimal
valid manifest (one downloaded WAV file, matching the function's own
docstring example), it crashes immediately:

```
AttributeError: 'NoneType' object has no attribute 'astype'
```

Root cause: it builds each row's audio column as
`{"path": str(local_path), "array": None}`, which is not a shape
`datasets.Audio.encode_example()` accepts — the installed version expects
either a bare path string or a real decoded array, not a `None` placeholder
alongside a path. This was never caught because the function had zero test
coverage — not even an `importorskip`-gated test existed for it.

By contrast, `export_attribution` (no third-party dependencies) already had
real passing tests, and `to_webdataset` — despite also lacking tests before
this restoration — was hand-verified against the real `webdataset` and
`soundfile` libraries and works correctly. Both now have CI coverage via the
`export` job in `.github/workflows/ci.yml`, which installs
`soundfetch[dev,export]` and runs `tests/unit/test_export.py` for real.

## Revisit triggers

Reconsider the adapters only when all of the following are available:

- concrete user demand for the specific framework;
- a named maintenance owner;
- documented supported dependency and version matrices;
- integration tests using the real optional dependency, run in CI; and
- an approved proposal for the public Python API and packaging extras.

Each adapter may be reconsidered independently; demand for one is not
evidence that all three should ship.

Reconsider `to_hf_dataset` once it's fixed (likely: supply a bare path
string, or a proper `{"path": ..., "bytes": ...}` shape, to the `Audio`
feature instead of the current `{"path", "array": None}` dict) and has a
real test — gated the same way `to_webdataset`'s now is — exercising it
against the installed `datasets` library in CI.

## Selective recovery

Do not merge `feat/agent-usability` wholesale: it contains unrelated work
that is already integrated or may have evolved. Recover only the approved
files from the retained source commit, for example:

```bash
git show 0c4a9b3:src/soundfetch/adapters/langchain.py > /tmp/soundfetch-langchain.py
git diff 0c4a9b3^ 0c4a9b3 -- src/soundfetch/adapters tests/unit/test_adapters.py
```

Review the historical implementation against the current manifest and public
API contracts, restore only the selected files and dependency group, add
real-dependency integration coverage that actually runs in CI, and run the
current verification suite. Treat restoration as a new public-API proposal
requiring semantic review.
