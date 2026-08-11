---
description: Reorient to Soundfetch's current repository state before substantive work.
disable-model-invocation: true
---

# Soundfetch orientation

## Live repository state

Repository root:

!`git rev-parse --show-toplevel`

Current branch:

!`git branch --show-current`

Working tree:

!`git status --short --branch`

Recent commits:

!`git log --oneline -5`

Unstaged diff summary:

!`git diff --stat`

Staged diff summary:

!`git diff --cached --stat`

## Recontextualize

Do not modify any files.

Use the live state above plus the smallest amount of repository reading necessary to determine where work currently stands.

Rules:

- `AGENTS.md` is the project engineering contract.
- Use `README.md` for current user-facing behavior and roadmap context.
- Treat `PLAN.md` only as a rough historical/design reference because it is known to be corrupted; verify important claims against current code.
- Never treat the root `freesound_download.py` as the active implementation.
- If the working tree contains changes, inspect the affected files and their relevant tests.
- If recent commits indicate an active task, inspect only enough surrounding code to understand it.
- Do not invent an active task if none is recorded or inferable.

Return a concise cold-entry briefing covering:

- Project
- Branch
- Working tree
- Recent work
- Likely current task, or explicitly say none is recorded
- Verification state, distinguishing known evidence from tests not run this session
- Risks and uncertainty
- Next action

If there is no active task, suggest at most three plausible next actions and clearly label them as suggestions rather than existing commitments.
