"""Unit tests for soundfetch.providers.freesound.auth.TokenStore."""

from __future__ import annotations

import stat
from pathlib import Path

from soundfetch.providers.freesound.auth import Token, TokenStore


def _token() -> Token:
    return Token(
        access_token="ACCESS", refresh_token="REFRESH", expires_at=9999999999.0, scope=""
    )


class TestTokenStoreSave:
    def test_file_is_created_owner_only(self, tmp_path: Path):
        """The token file must never have a window at default (umask) perms
        between creation and the permission narrowing (the M-10 finding)."""
        path = tmp_path / "config" / "freesound.json"
        TokenStore(path).save(_token())

        assert stat.S_IMODE(path.stat().st_mode) == 0o600

    def test_parent_dir_is_created_owner_only(self, tmp_path: Path):
        path = tmp_path / "config" / "freesound.json"
        TokenStore(path).save(_token())

        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700

    def test_round_trips_through_load(self, tmp_path: Path):
        path = tmp_path / "freesound.json"
        store = TokenStore(path)
        store.save(_token())

        loaded = store.load()
        assert loaded is not None
        assert loaded.access_token == "ACCESS"
        assert loaded.refresh_token == "REFRESH"

    def test_overwriting_an_existing_token_stays_owner_only(self, tmp_path: Path):
        path = tmp_path / "freesound.json"
        store = TokenStore(path)
        store.save(_token())
        path.chmod(0o644)  # simulate a pre-existing file with looser perms

        store.save(_token())

        assert stat.S_IMODE(path.stat().st_mode) == 0o600
