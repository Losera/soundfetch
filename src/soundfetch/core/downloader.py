"""Streaming file download with .part resume, checksum verify, atomic rename."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path

import requests

from .net import (
    HttpError,
    RateLimitError,
    _attach_retry_after,
    _parse_retry_after,
    parse_error,
)

log = logging.getLogger(__name__)

CHUNK = 64 * 1024


class DownloadError(Exception):
    """A download that could not be completed (after retries/verification)."""


class ChecksumMismatch(DownloadError):
    """Downloaded bytes do not match the provider's advertised checksum."""


def stream_to_file(
    url: str,
    dest: Path,
    *,
    session: requests.Session | None = None,
    headers: dict | None = None,
    checksum: str | None = None,
    attempts: int = 5,
    reporthook=None,
    limiter=None,
) -> int:
    """Stream `url` into `dest`, resuming from an existing `.part` file.

    Writes to `dest.with_suffix(dest.suffix + ".part")`, verifies the optional
    md5 `checksum`, then atomically renames to `dest`. Returns the completed
    destination file size, including bytes retained from a resumed partial.

    `reporthook(downloaded, total)` is called after each chunk (total may be
    -1 if the server omits Content-Length).

    ``limiter`` is a ``core.pacing.RateLimiter``; when given, one token is
    consumed before the request so downloads share the provider's bucket.
    """
    if limiter is not None:
        limiter.acquire()
    session = session or requests.Session()
    part = dest.with_name(dest.name + ".part")
    part.parent.mkdir(parents=True, exist_ok=True)

    resumed = 0
    if part.exists():
        resumed = part.stat().st_size
        if resumed:
            log.info("resuming %s from %d bytes", dest.name, resumed)

    last_exc: Exception | None = None
    for attempt in range(attempts):
        range_header = {"Range": f"bytes={resumed}-"} if resumed else {}
        request_headers = dict(headers or {})
        request_headers.update(range_header)
        try:
            resp = session.get(url, headers=request_headers, stream=True, timeout=60)
            if resp.status_code not in (200, 206):
                exc = parse_error(resp)
                _attach_retry_after(exc, resp)
                raise exc

            if resp.status_code == 206:
                resumed = 0  # server honored Range; treat as full stream below

            total = int(resp.headers.get("Content-Length") or -1)
            if reporthook:
                reporthook(0, total)

            mode = "ab" if part.exists() and resp.status_code == 206 else "wb"
            written = 0
            hasher = hashlib.md5()
            if checksum and mode == "ab":
                with open(part, "rb") as existing:
                    for chunk in iter(lambda: existing.read(CHUNK), b""):
                        hasher.update(chunk)
            with open(part, mode) as fh:
                for chunk in resp.iter_content(chunk_size=CHUNK):
                    if not chunk:
                        continue
                    fh.write(chunk)
                    hasher.update(chunk)
                    written += len(chunk)
                    if reporthook:
                        reporthook(written, total)

            if checksum and hasher.hexdigest() != checksum.lower():
                part.unlink(missing_ok=True)
                raise ChecksumMismatch(
                    f"md5 mismatch for {url}: got {hasher.hexdigest()}, "
                    f"expected {checksum}"
                )

            os.replace(part, dest)  # atomic rename
            return dest.stat().st_size

        except RateLimitError as exc:
            last_exc = exc
            retry_after = getattr(exc, "retry_after", None)
            if attempt + 1 >= attempts:
                break
            wait = _parse_retry_after(retry_after) or _backoff(attempt)
            log.warning("rate-limited; waiting %.1fs", wait)
            time.sleep(wait)
            # A 429 during range-resume may or may not have written anything;
            # resume from the current .part size on the next attempt.
            resumed = part.stat().st_size if part.exists() else 0
        except (HttpError, requests.RequestException) as exc:
            last_exc = exc
            if isinstance(exc, HttpError) and exc.status not in {500, 502, 503, 504}:
                break  # non-retryable status
            if attempt + 1 >= attempts:
                break
            time.sleep(_backoff(attempt))

    assert last_exc is not None
    raise DownloadError(str(last_exc)) from last_exc


def _backoff(attempt: int) -> float:
    return 0.5 * (2 ** attempt)
