---
name: orient
description: Perform Soundfetch's read-only cold-session repository orientation before substantive work.
---

Follow the Orientation Protocol in the repository's `AGENTS.md`.

Do not modify files.
Do not run tests or other verification during orientation.

Resolve the Git repository root first, even if Codex was launched from a
subdirectory.

Inspect existing live repository and Git state and return:

- Project
- Repository root
- Branch
- Working tree
- Recent work
- Current task, or explicitly state that none is established
- Verification state based only on existing evidence
- Risks / uncertainty
- Next action

Do not begin implementation.

Do not run tests merely to establish verification state. If current verification
evidence is unavailable, report it as unknown or not verified this session.
