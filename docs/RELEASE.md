# Release checklist

This checklist prepares and publishes a Soundfetch release. Run deterministic
checks before any live-provider check, and stop before tagging or publishing
unless a human has explicitly authorized that release action.

## 1. Preflight and version review

1. Start from the intended release branch and confirm `git status --short` is
   clean. Fetch the remote and review the branch relationship before building.
2. Review the complete semantic diff against the previous release. Obtain human
   approval for public API, manifest, provider, packaging, and release-process
   changes.
3. Confirm the release version agrees in `pyproject.toml` and
   `src/soundfetch/__init__.py`. Review the README and release notes for the same
   version and supported behavior.
4. Create a fresh worktree-local environment with
   `scripts/bootstrap-worktree.sh`. Confirm the reported `soundfetch` import is
   beneath that worktree.

## 2. Deterministic verification

Run the offline suite and the optional MCP checks:

```sh
.venv/bin/python -m pytest -m "not live"
.venv/bin/python -m pip install -e ".[mcp]"
.venv/bin/python -m pytest tests/unit/test_mcp.py
```

Install release tooling into the worktree-local environment, build both
distribution formats, and validate their metadata:

```sh
.venv/bin/python -m pip install build twine
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
```

Inspect `dist/` and confirm it contains exactly the expected wheel and source
archive for the reviewed version. Build artifacts are local outputs, not source
changes.

## 3. Wheel smoke test

Test the wheel rather than the checkout in a fresh environment. Replace the
wheel path if the version differs:

```sh
python -m venv /tmp/soundfetch-wheel-smoke
/tmp/soundfetch-wheel-smoke/bin/python -m pip install dist/soundfetch-*.whl
/tmp/soundfetch-wheel-smoke/bin/soundfetch --version
/tmp/soundfetch-wheel-smoke/bin/soundfetch --help
/tmp/soundfetch-wheel-smoke/bin/soundfetch sources --json
/tmp/soundfetch-wheel-smoke/bin/python -c 'import soundfetch, soundfetch.api, soundfetch.cli, soundfetch.core; print(soundfetch.__file__)'
```

Confirm the printed import path is inside `/tmp/soundfetch-wheel-smoke`, not the
checkout. These base imports must work without installing MCP or video extras.

## 4. Authorized live smoke

Only with deliberate authorization and network access, run a bounded Archive
search from the installed-wheel environment. Keep its output outside the
repository and record the command, output path, and result separately from the
deterministic checks:

```sh
/tmp/soundfetch-wheel-smoke/bin/soundfetch archive search rain \
  --max-results 1 --page-size 1 --json \
  > /tmp/soundfetch-archive-live-smoke.json
```

Do not put live searches in CI. Missing credentials or network access is a
reported limitation, not a successful check.

## 5. Human release gate

Before tagging, present the complete semantic diff and exact results from the
offline, MCP, build, twine, wheel, and any live checks. Resolve unexpected files
or failures and obtain explicit human authorization to tag and publish.

## 6. Tag and publish

After authorization, create the reviewed version tag and push it according to
the repository's protected-branch policy. Publish the already-validated files
from `dist/`; do not rebuild between approval and upload. Use the configured
trusted publisher or an explicitly authorized Twine credential flow.

After publication, verify the project page, version, rendered metadata, and both
distribution files on the package index. Install the published version into a
new empty environment, repeat the version/help/sources/import smoke checks, and
record the resulting import path and package-index URL.

## 7. Recovery

If a problem is found before publication, do not publish or reuse the version:
fix it on a reviewed branch, advance the version as required by the index, and
repeat every deterministic check.

If a published file is unsafe or materially broken, stop promotion and
downloads where possible, document the impact, and use the package index's yank
mechanism with explicit human authorization. A yank discourages normal
resolution but does not erase downloaded artifacts. Publish a corrected new
version; never overwrite an existing release file or move an existing tag.
