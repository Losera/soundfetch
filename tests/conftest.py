"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
import requests


@pytest.fixture
def outdir(tmp_path: Path) -> Path:
    return tmp_path / "out"


@pytest.fixture
def session() -> requests.Session:
    return requests.Session()
