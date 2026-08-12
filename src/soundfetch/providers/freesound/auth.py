"""Freesound OAuth2: browser code flow, token cache, auto-refresh.

Access tokens live 24h; the flow below caches the token (with its refresh
token) to `$SOUNDFETCH_CONFIG_DIR/freesound.json` (mode 0600) and transparently
refreshes when expired.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path

import requests

AUTHORIZE_URL = "https://freesound.org/apiv2/oauth2/authorize/"
TOKEN_URL = "https://freesound.org/apiv2/oauth2/access_token/"
DEFAULT_REDIRECT = "http://localhost:8765/callback"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "soundfetch"


@dataclass
class Token:
    access_token: str
    refresh_token: str | None
    expires_at: float  # epoch seconds
    scope: str = ""

    @classmethod
    def from_response(cls, payload: dict) -> "Token":
        expires_in = int(payload.get("expires_in", 86399))
        return cls(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_at=time.time() + expires_in,
            scope=payload.get("scope", ""),
        )

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at


class AuthError(Exception):
    """OAuth2 flow failed."""


class TokenStore:
    """Load/save the token cache with restrictive permissions."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Token | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text())
            return Token(
                access_token=payload["access_token"],
                refresh_token=payload.get("refresh_token"),
                expires_at=payload["expires_at"],
                scope=payload.get("scope", ""),
            )
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def save(self, token: Token) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        payload = {
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "expires_at": token.expires_at,
            "scope": token.scope,
        }
        data = json.dumps(payload).encode()
        # Create the file at 0600 from the start. write_text() + a
        # subsequent os.chmod() leaves a window — default umask permissions
        # until the chmod runs, or permanently if the process dies between
        # the two calls — where the access and refresh tokens are
        # world-readable.
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        # O_CREAT's mode only applies when the file didn't already exist —
        # an upgrade from a version that left a looser-permissioned file
        # behind wouldn't otherwise be tightened on the next save.
        os.chmod(self.path, 0o600)


class OAuthClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        redirect_uri: str = DEFAULT_REDIRECT,
        session: requests.Session | None = None,
        store: TokenStore | None = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.session = session or requests.Session()
        self.store = store or TokenStore(
            Path(os.environ.get("SOUNDFETCH_CONFIG_DIR", DEFAULT_CONFIG_DIR)) / "freesound.json"
        )

    def authorize_url(self) -> str:
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
        }
        req = requests.Request("GET", AUTHORIZE_URL, params=params).prepare()
        return req.url

    def get_token(self, *, refresh: bool = False) -> Token:
        """Return a valid token, refreshing if needed or forced."""
        token = None if refresh else self.store.load()
        if token and not token.expired:
            return token
        if token and token.refresh_token:
            return self._exchange_refresh(token.refresh_token)
        raise AuthError(
            "no usable Freesound token. Run `soundfetch freesound auth` first."
        )

    def _exchange_refresh(self, refresh_token: str) -> Token:
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        resp = self.session.post(TOKEN_URL, data=data, timeout=30)
        if resp.status_code != 200:
            raise AuthError(f"token refresh failed: HTTP {resp.status_code} {resp.text[:200]}")
        token = Token.from_response(resp.json())
        self.store.save(token)
        return token

    def run_code_flow(self, *, force: bool = False) -> Token:
        """Open the browser, catch the callback, exchange the code, cache the token."""
        url = self.authorize_url()
        print(f"Opening your browser to authorize soundfetch:\n{url}")
        print(f"(waiting for callback at {self.redirect_uri})")
        try:
            webbrowser.open(url)
        except Exception:
            print("Could not open a browser automatically — open the URL above manually.")

        code = _wait_for_code(self.redirect_uri)
        if code.startswith("error"):
            raise AuthError(f"authorization failed: {code}")

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }
        resp = self.session.post(TOKEN_URL, data=data, timeout=30)
        if resp.status_code != 200:
            raise AuthError(f"token exchange failed: HTTP {resp.status_code} {resp.text[:200]}")
        token = Token.from_response(resp.json())
        self.store.save(token)
        return token


def _wait_for_code(redirect_uri: str, timeout: float = 300.0) -> str:
    """Run a tiny localhost HTTP server and return the `code` query param."""
    from urllib.parse import parse_qs, urlparse

    import http.server
    import socketserver

    class Handler(http.server.BaseHTTPRequestHandler):
        result: str = ""

        def do_GET(self) -> None:  # noqa: N802
            parsed = parse_qs(urlparse(self.path).query)
            if "code" in parsed:
                Handler.result = parsed["code"][0]
            elif "error" in parsed:
                Handler.result = f"error:{parsed['error'][0]}"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            message = (
                "Authorization complete. You can close this tab."
                if not Handler.result.startswith("error")
                else f"Authorization failed: {Handler.result}"
            )
            self.wfile.write(f"<html><body>{message}</body></html>".encode())

        def log_message(self, *args) -> None:  # silence
            pass

    parsed = urlparse(redirect_uri)
    port = parsed.port or 8765

    if _port_in_use("localhost", port):
        raise AuthError(
            f"cannot start the OAuth callback server: port {port} is already in use.\n"
            f"Another soundfetch auth (or other process) is holding it — find it with\n"
            f"`lsof -i :{port}` and stop it, then re-run. The port comes from the\n"
            f"redirect URI, which must match your Freesound app registration exactly\n"
            f"(current: {redirect_uri})."
        )

    class Server(socketserver.TCPServer):
        allow_reuse_address = True

    try:
        httpd = Server(("localhost", port), Handler)
    except OSError as exc:
        raise AuthError(
            f"could not bind the OAuth callback server to localhost:{port} "
            f"({exc.strerror or exc}). Check that no other process is using the "
            f"port (`lsof -i :{port}`) and that --redirect-uri matches your "
            f"Freesound app registration."
        ) from exc

    with httpd:
        httpd.timeout = 0.5
        deadline = time.time() + timeout
        while time.time() < deadline:
            httpd.handle_request()
            if Handler.result:
                return Handler.result
    raise AuthError(f"timed out waiting for authorization callback at {redirect_uri}")


def _port_in_use(host: str, port: int) -> bool:
    """Return True if nothing can bind *host:port* right now."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
    except OSError:
        return True
    finally:
        sock.close()
    return False
