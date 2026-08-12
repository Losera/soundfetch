from __future__ import annotations

from pathlib import Path

import pytest

from soundfetch.core.names import sanitize_ext, sanitize_stem, unique_path


class TestSanitizeStem:
    def test_keeps_allowed_chars(self):
        assert sanitize_stem("Rain_on-Roof.01", "fallback") == "Rain_on-Roof.01"

    def test_collapses_disallowed_runs_to_single_underscore(self):
        assert sanitize_stem("field  recording / rain!!", "fallback") == "field_recording_rain"

    def test_strips_leading_and_trailing_junk(self):
        assert sanitize_stem("  ...weird name...  ", "fallback") == "weird_name"

    def test_caps_length(self):
        long_name = "a" * 500
        result = sanitize_stem(long_name, "fallback")
        assert len(result) <= 120

    def test_empty_result_falls_back(self):
        assert sanitize_stem("!!!///", "sound-42") == "sound-42"

    def test_empty_input_falls_back(self):
        assert sanitize_stem("", "sound-42") == "sound-42"


class TestUniquePath:
    def test_no_collision_uses_bare_name(self, tmp_path: Path):
        result = unique_path(tmp_path, "piano", "mp3")
        assert result == tmp_path / "piano.mp3"

    def test_collision_on_disk_appends_counter(self, tmp_path: Path):
        (tmp_path / "piano.mp3").write_text("x")
        result = unique_path(tmp_path, "piano", "mp3")
        assert result == tmp_path / "piano (1).mp3"

    def test_collision_in_taken_set_appends_counter(self, tmp_path: Path):
        result = unique_path(tmp_path, "piano", "mp3", taken={"piano.mp3"})
        assert result == tmp_path / "piano (1).mp3"

    def test_skips_multiple_existing_collisions(self, tmp_path: Path):
        (tmp_path / "piano.mp3").write_text("x")
        (tmp_path / "piano (1).mp3").write_text("x")
        result = unique_path(tmp_path, "piano", "mp3")
        assert result == tmp_path / "piano (2).mp3"

    def test_ext_leading_dot_is_stripped(self, tmp_path: Path):
        result = unique_path(tmp_path, "piano", ".mp3")
        assert result == tmp_path / "piano.mp3"

    def test_traversal_in_unsanitized_ext_is_rejected(self, tmp_path: Path):
        """A caller that skips sanitize_ext() must fail loudly rather than
        silently write outside dest_dir (the H-1 finding)."""
        with pytest.raises(ValueError, match="escapes destination directory"):
            unique_path(tmp_path, "piano", "../../../../etc/cron.d/evil")

    def test_traversal_in_unsanitized_stem_is_rejected(self, tmp_path: Path):
        with pytest.raises(ValueError, match="escapes destination directory"):
            unique_path(tmp_path, "../../../../etc/cron.d/evil", "mp3")


class TestSanitizeExt:
    def test_keeps_plain_extension(self):
        assert sanitize_ext("mp3", "bin") == "mp3"

    def test_strips_leading_dot(self):
        assert sanitize_ext(".wav", "bin") == "wav"

    def test_drops_traversal_and_separators(self):
        result = sanitize_ext("../../../../home/user/.bashrc", "bin")
        assert "/" not in result
        assert ".." not in result

    def test_none_falls_back(self):
        assert sanitize_ext(None, "bin") == "bin"

    def test_empty_falls_back(self):
        assert sanitize_ext("", "bin") == "bin"

    def test_only_junk_falls_back(self):
        assert sanitize_ext("../../", "bin") == "bin"

    def test_caps_length(self):
        result = sanitize_ext("a" * 100, "bin")
        assert len(result) <= 12

    def test_null_byte_is_dropped(self):
        result = sanitize_ext("mp3\x00.desktop", "bin")
        assert "\x00" not in result
