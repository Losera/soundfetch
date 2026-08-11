"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

import soundfetch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOUNDFETCH_PATH = Path(soundfetch.__file__).resolve()

try:
    SOUNDFETCH_PATH.relative_to(REPOSITORY_ROOT)
except ValueError:
    pytest.exit(
        "Soundfetch tests imported the package from another checkout: "
        f"{SOUNDFETCH_PATH}. Run scripts/bootstrap-worktree.sh in "
        f"{REPOSITORY_ROOT} and rerun tests with .venv/bin/python -m pytest.",
        returncode=2,
    )


@pytest.fixture
def outdir(tmp_path: Path) -> Path:
    return tmp_path / "out"


@pytest.fixture
def session() -> requests.Session:
    return requests.Session()
