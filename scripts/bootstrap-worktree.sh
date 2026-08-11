#!/usr/bin/env bash

set -euo pipefail

worktree_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_dir="${worktree_root}/.venv"

if [[ ! -x "${venv_dir}/bin/python" ]]; then
    python -m venv "${venv_dir}"
fi

"${venv_dir}/bin/python" -m pip install -e "${worktree_root}[dev]"
"${venv_dir}/bin/python" - "${worktree_root}" <<'PY'
from pathlib import Path
import sys

import soundfetch

worktree_root = Path(sys.argv[1]).resolve()
module_path = Path(soundfetch.__file__).resolve()
try:
    module_path.relative_to(worktree_root)
except ValueError:
    raise SystemExit(
        "worktree bootstrap failed: soundfetch imported from "
        f"{module_path}, not beneath {worktree_root}"
    )

print(f"soundfetch import: {module_path}")
PY
