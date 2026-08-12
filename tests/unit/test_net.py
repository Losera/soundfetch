from __future__ import annotations

import pytest
import requests

from soundfetch.core.net import HttpError, RateLimitError, get_json, retry
from soundfetch.core.net import _redact_url


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch: pytest.MonkeyPatch):
    """Every retry test exercises backoff/Retry-After logic; never actually wait."""
    sleeps: list[float] = []
    monkeypatch.setattr("soundfetch.core.net.time.sleep", lambda s: sleeps.append(s))
    return sleeps


class TestRetry:
    def test_succeeds_first_try_without_retrying(self):
        calls = []

        def fn():
            calls.append(1)
            return "ok"

        assert retry(fn) == "ok"
        assert len(calls) == 1

    def test_retries_retryable_status_then_succeeds(self):
        attempts = {"n": 0}

        def fn():
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise HttpError(503, "unavailable")
            return "ok"

        assert retry(fn, attempts=5) == "ok"
        assert attempts["n"] == 3

    def test_non_retryable_status_raises_immediately(self):
        calls = []

        def fn():
            calls.append(1)
            raise HttpError(404, "not found")

        with pytest.raises(HttpError):
            retry(fn, attempts=5)
        assert len(calls) == 1

    def test_exhausts_attempts_and_raises_last_exc(self):
        def fn():
            raise HttpError(500, "server error")

        with pytest.raises(HttpError):
            retry(fn, attempts=3)

    def test_rate_limit_honors_retry_after(self, no_real_sleep):
        attempts = {"n": 0}

        def fn():
            attempts["n"] += 1
            if attempts["n"] < 2:
                exc = RateLimitError(429, "slow down")
                exc.retry_after = "7"
                raise exc
            return "ok"

        assert retry(fn, attempts=5) == "ok"
        assert no_real_sleep == [7.0]

    def test_rate_limit_without_retry_after_uses_backoff(self, no_real_sleep):
        attempts = {"n": 0}

        def fn():
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise RateLimitError(429, "slow down")
            return "ok"

        assert retry(fn, attempts=5) == "ok"
        assert len(no_real_sleep) == 1
        assert no_real_sleep[0] > 0

    def test_connection_error_retries_then_raises_when_exhausted(self):
        def fn():
            raise requests.ConnectionError("refused")

        with pytest.raises(requests.ConnectionError):
            retry(fn, attempts=2)

    def test_custom_retry_on_set(self):
        calls = []

        def fn():
            calls.append(1)
            raise HttpError(418, "teapot")

        with pytest.raises(HttpError):
            retry(fn, attempts=3, retry_on={418})
        assert len(calls) == 3


class TestGetJson:
    def test_returns_parsed_body_on_200(self, session: requests.Session, requests_mock):
        requests_mock.get("https://example.test/thing", json={"ok": True})
        assert get_json(session, "https://example.test/thing") == {"ok": True}

    def test_retries_5xx_then_succeeds(self, session: requests.Session, requests_mock):
        requests_mock.get(
            "https://example.test/thing",
            [{"status_code": 503, "text": "busy"}, {"json": {"ok": True}, "status_code": 200}],
        )
        assert get_json(session, "https://example.test/thing", attempts=3) == {"ok": True}

    def test_raises_http_error_on_404(self, session: requests.Session, requests_mock):
        requests_mock.get("https://example.test/thing", status_code=404, json={"detail": "nope"})
        with pytest.raises(HttpError) as excinfo:
            get_json(session, "https://example.test/thing")
        assert "nope" in str(excinfo.value)


class TestRedactUrl:
    def test_redacts_token_param(self):
        result = _redact_url("https://freesound.org/apiv2/search/?query=x&token=SECRET123")
        assert "SECRET123" not in result
        assert "token=" in result

    def test_leaves_non_sensitive_params_alone(self):
        result = _redact_url("https://example.test/search?query=rain&page=2")
        assert "query=rain" in result
        assert "page=2" in result

    def test_no_query_string_is_unchanged(self):
        assert _redact_url("https://example.test/thing") == "https://example.test/thing"

    def test_empty_url_is_unchanged(self):
        assert _redact_url("") == ""


class TestHttpErrorRedaction:
    def test_query_string_secret_does_not_appear_in_message_or_url_attr(self):
        exc = HttpError(429, "Too Many Requests", "https://freesound.org/apiv2/search/?token=LEAKED_KEY")
        assert "LEAKED_KEY" not in str(exc)
        assert "LEAKED_KEY" not in exc.url

    def test_this_is_what_a_real_freesound_429_would_have_leaked(
        self, session: requests.Session, requests_mock
    ):
        """End-to-end: a rate-limited search must not leak the API key
        through get_json()'s HttpError, even if some future call site puts
        the key back in the query string."""
        requests_mock.get(
            "https://freesound.org/apiv2/search/",
            status_code=429,
            json={"detail": "Request was throttled."},
        )
        with pytest.raises(HttpError) as excinfo:
            get_json(
                session,
                "https://freesound.org/apiv2/search/",
                params={"query": "rain", "token": "sk-real-secret-key"},
            )
        assert "sk-real-secret-key" not in str(excinfo.value)
