from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import requests

from soundfetch.core.downloader import ChecksumMismatch, DownloadError, stream_to_file


class TestStreamToFile:
    def test_writes_dest_and_removes_part_file(self, tmp_path: Path, session: requests.Session, requests_mock):
        dest = tmp_path / "sound.mp3"
        requests_mock.get("https://example.test/file", content=b"hello world")

        written = stream_to_file("https://example.test/file", dest, session=session)

        assert written == len(b"hello world")
        assert dest.read_bytes() == b"hello world"
        assert not dest.with_name(dest.name + ".part").exists()

    def test_range_resume_appends_to_existing_part(
        self, tmp_path: Path, session: requests.Session, requests_mock
    ):
        dest = tmp_path / "sound.mp3"
        part = dest.with_name(dest.name + ".part")
        part.write_bytes(b"HELLO")
        remaining = b" WORLD"

        def callback(request, context):
            assert request.headers.get("Range") == "bytes=5-"
            context.status_code = 206
            return remaining

        requests_mock.get("https://example.test/file", content=callback)

        written = stream_to_file("https://example.test/file", dest, session=session)

        assert written == len(remaining)
        assert dest.read_bytes() == b"HELLO WORLD"
        assert not part.exists()

    def test_range_resume_verifies_checksum_of_complete_file(
        self, tmp_path: Path, session: requests.Session, requests_mock
    ):
        dest = tmp_path / "sound.mp3"
        part = dest.with_name(dest.name + ".part")
        part.write_bytes(b"HELLO")
        remaining = b" WORLD"
        checksum = hashlib.md5(b"HELLO WORLD").hexdigest()

        def callback(request, context):
            assert request.headers.get("Range") == "bytes=5-"
            context.status_code = 206
            return remaining

        requests_mock.get("https://example.test/file", content=callback)

        written = stream_to_file(
            "https://example.test/file",
            dest,
            session=session,
            checksum=checksum,
        )

        assert written == len(remaining)
        assert dest.read_bytes() == b"HELLO WORLD"
        assert not part.exists()

    def test_checksum_match_succeeds(self, tmp_path: Path, session: requests.Session, requests_mock):
        dest = tmp_path / "sound.mp3"
        content = b"lossless bytes"
        checksum = hashlib.md5(content).hexdigest()
        requests_mock.get("https://example.test/file", content=content)

        written = stream_to_file(
            "https://example.test/file", dest, session=session, checksum=checksum
        )

        assert written == len(content)
        assert dest.read_bytes() == content

    def test_checksum_mismatch_raises_and_cleans_up_part(
        self, tmp_path: Path, session: requests.Session, requests_mock
    ):
        dest = tmp_path / "sound.mp3"
        requests_mock.get("https://example.test/file", content=b"corrupted bytes")

        with pytest.raises(ChecksumMismatch):
            stream_to_file(
                "https://example.test/file",
                dest,
                session=session,
                checksum="0" * 32,
            )

        assert not dest.exists()
        assert not dest.with_name(dest.name + ".part").exists()

    def test_non_retryable_http_error_raises_download_error(
        self, tmp_path: Path, session: requests.Session, requests_mock
    ):
        dest = tmp_path / "sound.mp3"
        requests_mock.get("https://example.test/file", status_code=404, text="not found")

        with pytest.raises(DownloadError):
            stream_to_file("https://example.test/file", dest, session=session)

    def test_timeout_is_wrapped_as_download_error(
        self, tmp_path: Path, session: requests.Session, requests_mock
    ):
        dest = tmp_path / "sound.mp3"
        timeout = requests.Timeout("timed out")
        requests_mock.get("https://example.test/file", exc=timeout)

        with pytest.raises(DownloadError) as caught:
            stream_to_file(
                "https://example.test/file",
                dest,
                session=session,
                attempts=1,
            )

        assert caught.value.__cause__ is timeout

    def test_retries_5xx_then_succeeds(
        self, tmp_path: Path, session: requests.Session, requests_mock, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr("soundfetch.core.downloader.time.sleep", lambda s: None)
        dest = tmp_path / "sound.mp3"
        requests_mock.get(
            "https://example.test/file",
            [
                {"status_code": 503, "text": "busy"},
                {"content": b"hello world", "status_code": 200},
            ],
        )

        written = stream_to_file("https://example.test/file", dest, session=session, attempts=3)

        assert written == len(b"hello world")
        assert dest.read_bytes() == b"hello world"
