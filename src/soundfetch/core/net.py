"""HTTP helpers: retry with Retry-After / exponential backoff, error parsing."""

from __future__ import annotations

import logging
import random
import time
from email.utils import parsedate_to_datetime
from typing import Callable, TypeVar
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests

log = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# Query-parameter names that commonly carry credentials. A provider API key
# or session token in the query string (Freesound's `token=`, a signed
# download URL's `key=`, ...) must never survive into an error message: that
# message can land in an MCP tool response shown to a model, in a shared
# manifest.jsonl, or in a log file.
_SENSITIVE_PARAMS = {
    "token", "api_key", "apikey", "key", "secret",
    "access_token", "client_secret", "password", "auth",
}

T = TypeVar("T")


def _redact_url(url: str) -> str:
    """Replace sensitive query-parameter values in `url` with `***`."""
    if not url or "?" not in url:
        return url
    parsed = urlsplit(url)
    if not parsed.query:
        return url
    params = parse_qsl(parsed.query, keep_blank_values=True)
    redacted = [
        (k, "***" if k.lower() in _SENSITIVE_PARAMS else v) for k, v in params
    ]
    return urlunsplit(parsed._replace(query=urlencode(redacted)))


class HttpError(Exception):
    """A failed HTTP call with a readable message."""

    def __init__(self, status: int | None, reason: str, url: str = ""):
        self.status = status
        self.reason = reason
        self.url = _redact_url(url)
        msg = f"HTTP {status} {reason}" if status else reason
        if self.url:
            msg += f" ({self.url})"
        super().__init__(msg)


class RateLimitError(HttpError):
    """Server asked us to slow down (429)."""


def parse_error(response: requests.Response) -> HttpError:
    status = response.status_code
    reason = response.reason or "error"
    # Freesound/archive error bodies are {"detail": "..."} or plain text.
    try:
        body = response.json()
        detail = body.get("detail") or body.get("error") or body.get("message")
        if detail:
            reason = str(detail)
    except ValueError:
        text = response.text.strip()
        if text and len(text) < 200:
            reason = text
    if status == 429:
        return RateLimitError(status, reason, response.url)
    return HttpError(status, reason, response.url)


def _sleep_with_jitter(base_delay: float, attempt: int) -> None:
    delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
    log.warning("retrying in %.1fs", delay)
    time.sleep(delay)


def retry(
    fn: Callable[[], T],
    *,
    attempts: int = 5,
    base_delay: float = 0.5,
    retry_on: set[int] | None = None,
) -> T:
    """Call fn, retrying on retryable statuses (honoring Retry-After) and
    ConnectionError. `fn` must raise HttpError or requests.ConnectionError."""
    retry_on = retry_on or RETRYABLE_STATUS
    last_exc: Exception | None = None

    for attempt in range(attempts):
        try:
            return fn()
        except RateLimitError as exc:
            last_exc = exc
            retry_after = _retry_after_seconds(exc)
            if attempt + 1 >= attempts:
                break
            if retry_after:
                log.warning("rate-limited; waiting %ss (Retry-After)", retry_after)
                time.sleep(retry_after)
            else:
                _sleep_with_jitter(base_delay, attempt)
        except HttpError as exc:
            last_exc = exc
            if exc.status not in retry_on or attempt + 1 >= attempts:
                raise
            _sleep_with_jitter(base_delay, attempt)
        except requests.ConnectionError as exc:
            last_exc = exc
            if attempt + 1 >= attempts:
                break
            _sleep_with_jitter(base_delay, attempt)

    assert last_exc is not None
    raise last_exc


def _parse_retry_after(value: str | None, *, now: float | None = None) -> float:
    """Parse a Retry-After header into seconds.

    Accepts either a bare integer (``"3"``) or an HTTP-date
    (``"Fri, 31 Dec 1999 23:59:59 GMT"``, per RFC 7231). HTTP-dates are
    normalized to UTC and expressed as seconds-from-now. Any value over
    300 s is capped so a misbehaving server can't stall a run.
    """
    if not value:
        return 0.0
    now = time.time() if now is None else now
    try:
        seconds = float(value)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                when = when.replace(tzinfo=ZoneInfo("UTC"))
            when_utc = when.astimezone(ZoneInfo("UTC"))
            seconds = (when_utc.timestamp() - now)
        except (TypeError, ValueError, OverflowError):
            return 0.0
    return max(0.0, min(300.0, seconds))


def _retry_after_seconds(exc: RateLimitError) -> float:
    """Re-read the Retry-After header from the request the error came from.

    We stash the response header on the exception via a wrapper attribute set
    by the request helpers below.
    """
    return _parse_retry_after(getattr(exc, "retry_after", None))


def get_json(
    session: requests.Session,
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    attempts: int = 5,
    limiter=None,
) -> dict:
    """GET JSON with retry; returns the parsed body.

    ``limiter`` is a ``core.pacing.RateLimiter`` (or anything with an
    ``acquire()``); when given, one token is consumed before each HTTP
    call so paging/search/download all share a per-provider bucket.
    """
    if limiter is not None:
        limiter.acquire()
    return retry(
        lambda: _get_json_once(session, url, params=params, headers=headers),
        attempts=attempts,
    )


def _get_json_once(
    session: requests.Session, url: str, *, params: dict | None, headers: dict | None
) -> dict:
    resp = session.get(url, params=params, headers=headers, timeout=30)
    if resp.status_code != 200:
        exc = parse_error(resp)
        _attach_retry_after(exc, resp)
        raise exc
    return resp.json()


def _attach_retry_after(exc: HttpError, resp: requests.Response) -> None:
    value = resp.headers.get("Retry-After")
    if value:
        exc.retry_after = value  # type: ignore[attr-defined]
