"""Browser-based login (`studylife login`).

Ported from studylife-mcp's own login.py (same repo family, see that file for the original
identity-contract-v1 §2 round trip this generalizes), with two real differences:

1. Talks to the GENERIC dynamic-client flow (`/connect/client/{client_id}`, `POST
   /api/auth/connect`/`/api/auth/assertion-exchange`) instead of the hardcoded "mcp" audience -
   piggybacking on "mcp" would rotate studylife-mcp's own shared key slot out from under it.
2. Binds one of a small FIXED set of candidate loopback ports instead of an OS-assigned random
   one. The generic flow validates redirect_uri by EXACT match against the client's own
   registered AllowedRedirectUris (stricter than the old audiences' blanket https-or-loopback
   check) - a random port could never match a single pre-registered URI, so this client is
   registered (once, via studylife-developers) with several fixed candidate ports instead, and
   tries each in turn until one is free.
"""

from __future__ import annotations

import hmac
import secrets
import sys
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from studylife_cli.credentials import Credentials, save_credentials

# Fixed candidate ports, tried in order - must match (a subset of) the AllowedRedirectUris
# registered for this ClientId on the target instance. Kept small and low-numbered enough to
# rarely collide with something else already running locally.
CANDIDATE_PORTS = (8765, 8766, 8767, 8768)

CALLBACK_TIMEOUT_SECONDS = 300.0

DEFAULT_CLIENT_ID = "studylife-cli"


class LoginError(Exception):
    """Raised on any failure of the login round trip, carrying a human-readable reason."""


@dataclass
class CallbackResult:
    """What the loopback callback received, before any validation - state/assertion default to
    "" (not missing) so callers can treat "" uniformly as "not provided"."""

    state: str
    assertion: str


def _parse_callback_query(query_string: str) -> CallbackResult:
    query = parse_qs(query_string)
    return CallbackResult(
        state=query.get("state", [""])[0],
        assertion=query.get("assertion", [""])[0],
    )


def _states_match(received: str, expected: str) -> bool:
    """Constant-time comparison - the state isn't secret, but there's no reason to prefer a
    timing-observable comparison over a safe one that's just as easy to write."""
    return hmac.compare_digest(received, expected)


_CALLBACK_PAGE = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>studylife-cli login</title></head>
<body style="font-family: sans-serif; text-align: center; padding-top: 3rem;">
<p>Login complete &mdash; you can close this tab and return to the terminal.</p>
</body>
</html>
"""


class _CallbackState:
    """Shared between the HTTP handler (invoked synchronously inside
    HTTPServer.handle_request()) and the caller waiting on it - a single request is ever served
    per listener instance, so a plain attribute is enough."""

    def __init__(self) -> None:
        self.result: CallbackResult | None = None


def _make_handler(state: _CallbackState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass  # Silence the default stderr access log - nothing useful, just noise.

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return

            state.result = _parse_callback_query(parsed.query)

            body = _CALLBACK_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


class _LoopbackHTTPServer(HTTPServer):
    """HTTPServer normally sets allow_reuse_address=1, which on Windows lets a second listener
    silently bind the exact same port instead of raising - the opposite of what
    `_bind_first_free_port`'s try-the-next-candidate fallback needs. Disabling it makes "is this
    port already taken" behave the same (a real OSError) on every platform."""

    allow_reuse_address = False


class _CallbackHTTPServer:
    """Localhost-only (127.0.0.1) HTTP listener on one of CANDIDATE_PORTS for the single
    `/callback` request the generic consent page redirects the browser to. Serves exactly one
    request: `wait_for_callback()` blocks until it arrives (or the given timeout elapses)."""

    def __init__(self, port: int) -> None:
        self._state = _CallbackState()
        self._server = _LoopbackHTTPServer(("127.0.0.1", port), _make_handler(self._state))

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def wait_for_callback(self, timeout_seconds: float) -> CallbackResult | None:
        self._server.timeout = timeout_seconds
        self._server.handle_request()  # returns on request OR timeout, whichever first
        self._server.server_close()
        return self._state.result


def _bind_first_free_port(candidates: tuple[int, ...]) -> _CallbackHTTPServer:
    last_error: OSError | None = None
    for port in candidates:
        try:
            return _CallbackHTTPServer(port)
        except OSError as exc:
            last_error = exc
            continue
    raise LoginError(
        f"None of the candidate ports {list(candidates)} are free on 127.0.0.1. "
        "Close whatever else is using them and try again."
    ) from last_error


def run_login(
    *,
    instance_url: str,
    client_id: str = DEFAULT_CLIENT_ID,
    candidate_ports: tuple[int, ...] = CANDIDATE_PORTS,
    timeout_seconds: float = CALLBACK_TIMEOUT_SECONDS,
    open_browser: Callable[[str], bool] = webbrowser.open,
) -> Credentials:
    """Drives one full browser login round trip and returns the resulting Credentials. Raises
    LoginError on any failure - callers decide how to present that (CLI prints and exits 1)."""
    base_url = instance_url.rstrip("/")
    state_token = secrets.token_urlsafe(32)

    callback_server = _bind_first_free_port(candidate_ports)
    redirect_uri = f"http://127.0.0.1:{callback_server.port}/callback"
    connect_url = (
        f"{base_url}/connect/client/{client_id}?"
        f"{urlencode({'redirect_uri': redirect_uri, 'state': state_token})}"
    )

    print(f"Opening your browser to log in to StudyLife:\n  {connect_url}")
    print("Waiting for you to finish logging in and approving the connection...")
    open_browser(connect_url)

    result = callback_server.wait_for_callback(timeout_seconds)
    if result is None:
        raise LoginError(
            f"Timed out after {int(timeout_seconds)}s waiting for StudyLife to redirect back. "
            "Either the login/approval wasn't completed in the browser tab, or this client "
            f"isn't registered on that instance yet - see the README for how to register "
            f"'{client_id}' via studylife-developers first."
        )

    if not _states_match(result.state, state_token):
        raise LoginError(
            "Rejected the login callback: its state didn't match what this command sent "
            "(possible cross-request mix-up). Please run this command again."
        )

    if not result.assertion:
        raise LoginError(
            "StudyLife's callback didn't include a login assertion - the connection may have "
            "been denied."
        )

    user_id, api_key = _exchange_assertion(base_url, client_id, result.assertion)
    del user_id  # not needed locally - kept for symmetry with the server's response shape
    return Credentials(instance_url=base_url, client_id=client_id, api_key=api_key)


def _exchange_assertion(base_url: str, client_id: str, assertion: str) -> tuple[int, str]:
    """Server-to-server exchange of the single-use assertion for the user id and a freshly
    issued, per-installation API key (generic flow - AuthController.10.OAuthClients.cs). No
    X-Api-Key is sent: this endpoint is [AllowAnonymous] by design, the assertion itself is the
    one-time credential."""
    try:
        response = httpx.post(
            f"{base_url}/api/auth/assertion-exchange",
            json={"clientId": client_id, "assertion": assertion},
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise LoginError(f"Could not reach StudyLife: {exc}") from exc

    if response.status_code != 200:
        raise LoginError(
            f"StudyLife rejected the login ({response.status_code}): {response.text.strip()}"
        )

    try:
        data = response.json()
        return int(data["userId"]), str(data["apiKey"])
    except (KeyError, TypeError, ValueError) as exc:
        raise LoginError("StudyLife returned an unexpected response shape.") from exc


def login_and_save(instance_url: str, client_id: str = DEFAULT_CLIENT_ID) -> Credentials:
    credentials = run_login(instance_url=instance_url, client_id=client_id)
    save_credentials(credentials)
    return credentials


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: python -m studylife_cli.login <instance-url>", file=sys.stderr)
        sys.exit(1)
    try:
        creds = login_and_save(sys.argv[1])
    except LoginError as exc:
        print(f"Login failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Login successful - credentials saved for {creds.instance_url}.")
