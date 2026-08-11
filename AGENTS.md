Soundfetch Agent Guide
Project

soundfetch is a Python CLI/library for searching multiple sound-data providers, downloading audio, and maintaining an append-only JSONL manifest.

User-facing behavior and usage live in README.md.

PLAN.md is a rough historical/design guide and is known to contain corrupted text. Never treat it as ground truth without checking the current code.

The root freesound_download.py is legacy pre-rewrite code. Do not extend or repair it unless explicitly asked. Current development lives under src/soundfetch/.

Orientation

Before substantive work in a fresh session:

Identify the current branch.
Inspect git status.
Inspect recent commits.
Inspect uncommitted/staged diff summaries.
Read only the documentation and source files needed to understand the active task.
Identify the relevant tests.
Report current state and next action before editing.

Claude Code users should invoke /orient.

Other runtimes should perform the equivalent steps directly.

Do not modify files during orientation.

Architecture invariants

The provider/core split is load-bearing.

Before modifying provider architecture, read src/soundfetch/core/provider.py.

Keep provider-independent behavior in core.

Search/download orchestration, pagination, resume behavior, and checkpointing belong in the shared engine rather than duplicated inside CLI/provider implementations.

The JSONL manifest is append-only and last-record-wins per sound identity. Treat its schema and checkpoint behavior as a compatibility boundary.

Providers should map provider-specific API responses into the shared core models rather than leaking provider payload structures through core logic. Keep the manifest envelope centralized in `core.engine.ref_record()` and provider-specific fields inside `SoundRef.metadata`.

Do not create provider-specific CLI implementations when the existing spec-driven/provider abstraction can express the behavior.

Keep provider loading lazy in both the core registry and CLI factories so commands that do not use a provider still work without that provider's optional dependencies.

Provider downloads should use the shared `core.downloader.stream_to_file()` path, or preserve its partial-file resume, checksum, retry, and atomic-replace guarantees. Unrecoverable per-item download failures intended for engine checkpointing must surface as `DownloadError`.

Preserve Freesound's `gen_ai_preference` in `SoundRef.metadata` and therefore in the manifest; it is compliance-relevant collection metadata.

Development

Each worktree must use its own `.venv`. Do not reuse or activate an environment
whose editable Soundfetch install points at another checkout. Bootstrap a new
worktree with:

scripts/bootstrap-worktree.sh

The script installs `.[dev]` and verifies that `soundfetch.__file__` resolves
beneath the current worktree. Run project commands through that environment,
for example `.venv/bin/python -m pytest`.

Manual install:

python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"

Default offline suite:

pytest -m "not live"

Targeted test:

pytest path/to/test_file.py::test_name

Live tests:

pytest -m live

Live tests use real network services and should only be run deliberately.

Verification

For a narrow change:

run the closest targeted test
run pytest -m "not live"
inspect the diff

For a bug fix, add or update a regression test when practical.

Never claim live-provider behavior was verified unless the relevant live test actually ran.

Git

Use a task branch for nontrivial features/fixes.

Use a worktree only for parallel agents, risky experiments, or weak/unproven models receiving edit access.

Minimal verified changes may be committed automatically under the global policy.

Substantive changes wait for human semantic diff review.

Architecture changes

Changes to provider boundaries, manifest semantics, public API shape, or major engine responsibilities count as architectural/system-design work.

Before implementing them, present alternatives, tradeoffs, risks, and a recommendation and wait for approval.
