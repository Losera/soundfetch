# Contributing to Soundfetch

Soundfetch welcomes focused fixes, tests, documentation, and provider-quality
improvements. Open an issue before proposing a new provider, public contract,
or architectural boundary.

## Development setup

```bash
git clone https://github.com/Losera/soundfetch.git
cd soundfetch
scripts/bootstrap-worktree.sh
.venv/bin/python -m pytest -m "not live"
```

Use a task branch and keep changes scoped. Bug fixes should include a regression
test when practical. Live tests access real services and must be run deliberately
with `.venv/bin/python -m pytest -m live`.

## Design constraints

- Keep provider-independent orchestration in `src/soundfetch/core/`.
- Preserve the append-only, last-record-wins manifest contract.
- Keep optional providers and integrations lazily loaded.
- Preserve downloader resume, checksum, retry, and atomic-replace guarantees.
- Treat remote metadata, URLs, filenames, credentials, and downloaded media as
  untrusted inputs.

Before opening a pull request, run the closest targeted test, the offline suite,
the public-API type check below, and `git diff --check`.

```bash
.venv/bin/python -m mypy src/soundfetch/__init__.py src/soundfetch/api.py \
  src/soundfetch/core/model.py src/soundfetch/core/provider.py \
  src/soundfetch/mcp.py
```

Explain the semantic change, verification performed,
and any remaining risk in the pull-request description.
