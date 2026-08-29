from __future__ import annotations

import threading
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import urlopen

import httpx
import pytest

from studylife_cli.login import (
    CANDIDATE_PORTS,
    LoginError,
    _bind_first_free_port,
    _parse_callback_query,
    _states_match,
    run_login,
)


def test_parse_callback_query_extracts_state_and_assertion() -> None:
    result = _parse_callback_query("state=abc&assertion=def")
    assert result.state == "abc"
    assert result.assertion == "def"


def test_parse_callback_query_defaults_missing_fields_to_empty_string() -> None:
    result = _parse_callback_query("")
    assert result.state == ""
    assert result.assertion == ""


def test_states_match() -> None:
    assert _states_match("token", "token")
    assert not _states_match("token", "other")


def test_bind_first_free_port_skips_occupied_ports() -> None:
    occupied = _bind_first_free_port(CANDIDATE_PORTS)
    try:
        server = _bind_first_free_port(CANDIDATE_PORTS)
        try:
            assert server.port != occupied.port
            assert server.port in CANDIDATE_PORTS
        finally:
            server._server.server_close()
    finally:
        occupied._server.server_close()


def test_bind_first_free_port_raises_when_all_occupied() -> None:
    servers = [_bind_first_free_port((port,)) for port in CANDIDATE_PORTS]
    try:
        with pytest.raises(LoginError):
            _bind_first_free_port(CANDIDATE_PORTS)
    finally:
        for server in servers:
            server._server.server_close()


def _extract_port(connect_url: str) -> int:
    redirect_uri = parse_qs(urlparse(connect_url).query)["redirect_uri"][0]
    return int(urlparse(redirect_uri).port)


def _trigger_callback(port: int, *, state: str, assertion: str) -> None:
    url = f"http://127.0.0.1:{port}/callback?{urlencode({'state': state, 'assertion': assertion})}"
    urlopen(url, timeout=5).read()


def test_run_login_completes_full_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    opened_urls: list[str] = []

    def fake_open_browser(url: str) -> bool:
        opened_urls.append(url)
        query = url.split("?", 1)[1]
        state = _parse_callback_query(query).state
        port = _extract_port(url)
        threading.Thread(
            target=_trigger_callback,
            args=(port,),
            kwargs={"state": state, "assertion": "the-assertion"},
        ).start()
        return True

    def fake_post(url: str, json: dict[str, object], timeout: float) -> httpx.Response:
        assert json == {"clientId": "studylife-cli", "assertion": "the-assertion"}
        return httpx.Response(200, json={"userId": 1, "apiKey": "the-api-key"})

    monkeypatch.setattr("studylife_cli.login.httpx.post", fake_post)

    credentials = run_login(
        instance_url="https://studylife.example.com",
        open_browser=fake_open_browser,
        timeout_seconds=5.0,
    )

    assert credentials.instance_url == "https://studylife.example.com"
    assert credentials.client_id == "studylife-cli"
    assert credentials.api_key == "the-api-key"
    assert len(opened_urls) == 1


def test_run_login_rejects_mismatched_state(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_open_browser(url: str) -> bool:
        port = _extract_port(url)
        threading.Thread(
            target=_trigger_callback,
            args=(port,),
            kwargs={"state": "wrong-state", "assertion": "x"},
        ).start()
        return True

    with pytest.raises(LoginError, match="state"):
        run_login(
            instance_url="https://studylife.example.com",
            open_browser=fake_open_browser,
            timeout_seconds=5.0,
        )


def test_run_login_times_out_when_browser_never_calls_back() -> None:
    with pytest.raises(LoginError, match="Timed out"):
        run_login(
            instance_url="https://studylife.example.com",
            open_browser=lambda url: True,
            timeout_seconds=0.2,
        )
