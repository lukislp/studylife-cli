from __future__ import annotations

from datetime import datetime, timedelta

import httpx
import pytest
import respx

from studylife_cli.client import StudyLifeClient
from studylife_cli.credentials import Credentials
from studylife_cli.models import Session
from studylife_cli.tui import (
    StudyLifeTUI,
    _format_duration,
    _next_upcoming_session,
    _sum_session_minutes,
    load_stats,
)

BASE_URL = "https://studylife.example.com"


def _session(start: datetime, end: datetime, course_name: str = "Analysis") -> Session:
    return Session(id=1, course_id=1, course_name=course_name, start_time=start, end_time=end)


def test_format_duration_minutes_only() -> None:
    assert _format_duration(45) == "45m"


def test_format_duration_hours_and_minutes() -> None:
    assert _format_duration(90) == "1h 30m"


def test_format_duration_whole_hours() -> None:
    assert _format_duration(120) == "2h"


def test_sum_session_minutes_completed_session() -> None:
    start = datetime.now() - timedelta(hours=2)
    end = start + timedelta(minutes=45)
    assert _sum_session_minutes([_session(start, end)]) == 45


def test_sum_session_minutes_clamps_in_progress_session_to_now() -> None:
    """Regression (mirrors studylife-alexa's own fix): a session fetched with
    only_completed=False can have an end_time in the future (still running) - must
    count elapsed time so far, not the full scheduled duration."""
    start = datetime.now() - timedelta(hours=2)
    scheduled_end = datetime.now() + timedelta(hours=3)
    minutes = _sum_session_minutes([_session(start, scheduled_end)])
    assert 115 <= minutes <= 121  # ~2h elapsed, not the full 5h block


def test_sum_session_minutes_ignores_not_yet_started_session() -> None:
    start = datetime.now() + timedelta(hours=1)
    end = start + timedelta(hours=1)
    assert _sum_session_minutes([_session(start, end)]) == 0


def test_next_upcoming_session_picks_nearest_future() -> None:
    far = _session(
        datetime.now() + timedelta(days=2), datetime.now() + timedelta(days=2, hours=1), "Far"
    )
    near = _session(
        datetime.now() + timedelta(hours=1), datetime.now() + timedelta(hours=2), "Near"
    )
    past = _session(
        datetime.now() - timedelta(hours=2), datetime.now() - timedelta(hours=1), "Past"
    )

    result = _next_upcoming_session([far, near, past])

    assert result is not None
    assert result.course_name == "Near"


def test_next_upcoming_session_none_when_nothing_scheduled() -> None:
    past = _session(datetime.now() - timedelta(hours=2), datetime.now() - timedelta(hours=1))
    assert _next_upcoming_session([past]) is None


@respx.mock
def test_load_stats_with_metrics_available() -> None:
    respx.get(
        f"{BASE_URL}/api/sessions/history", params={"days": "1", "onlyCompleted": "false"}
    ).mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE_URL}/api/timerstate").mock(
        return_value=httpx.Response(
            200,
            json={
                "sessionId": None,
                "isRunning": True,
                "isBreak": False,
                "currentRound": 1,
                "timerModeId": 0,
            },
        )
    )
    respx.get(f"{BASE_URL}/api/sessions").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE_URL}/api/coursegoals").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"courseId": 1, "courseName": "A", "completedAt": None},
                {"courseId": 2, "courseName": "B", "completedAt": "2026-08-01T00:00:00"},
            ],
        )
    )
    respx.get(f"{BASE_URL}/api/metrics/summary").mock(
        return_value=httpx.Response(
            200,
            json={
                "asOf": "2026-08-31T12:00:00",
                "program": {"id": None, "name": "Applied AI", "isBuiltIn": True},
                "streak": {"current": 7, "longest": 10},
                "hours": {"week": 5.5, "month": 20.0, "total": 100.0, "totalSessions": 40},
                "ects": {"earned": 30, "total": 180},
            },
        )
    )

    with StudyLifeClient(BASE_URL, api_key="test-key") as client:
        stats = load_stats(client)

    assert stats.metrics_available is True
    assert stats.streak_current == 7
    assert stats.week_hours == 5.5
    assert stats.ects_earned == 30
    assert stats.ects_total == 180
    assert stats.open_goals == 1
    assert stats.total_goals == 2
    assert stats.timer.is_running is True


@respx.mock
def test_load_stats_falls_back_gracefully_without_metrics_scope() -> None:
    respx.get(
        f"{BASE_URL}/api/sessions/history", params={"days": "1", "onlyCompleted": "false"}
    ).mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE_URL}/api/timerstate").mock(
        return_value=httpx.Response(
            200,
            json={
                "sessionId": None,
                "isRunning": False,
                "isBreak": False,
                "currentRound": 0,
                "timerModeId": 0,
            },
        )
    )
    respx.get(f"{BASE_URL}/api/sessions").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE_URL}/api/coursegoals").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE_URL}/api/metrics/summary").mock(
        return_value=httpx.Response(403, text="forbidden")
    )

    with StudyLifeClient(BASE_URL, api_key="test-key") as client:
        stats = load_stats(client)  # must not raise

    assert stats.metrics_available is False
    assert stats.streak_current == 0
    assert stats.ects_total == 0


@respx.mock
async def test_app_mounts_and_shows_loading_panels(monkeypatch: pytest.MonkeyPatch) -> None:
    """Smoke test: catches a typo'd widget id / CSS error / bad compose() wiring that
    unit tests of the pure functions above can't - doesn't wait for the background
    refresh worker to complete, only that the app mounts without crashing."""
    monkeypatch.setattr(
        "studylife_cli.tui.load_credentials",
        lambda: Credentials(instance_url=BASE_URL, client_id="studylife-cli", api_key="test-key"),
    )
    # The app kicks off a real refresh worker on mount - mock its endpoints so that
    # worker doesn't error out in the background during the test (ApiError there is
    # swallowed into an on-screen error message, not raised, but this keeps the test
    # from depending on unmocked-request behavior).
    respx.get(
        f"{BASE_URL}/api/sessions/history", params={"days": "1", "onlyCompleted": "false"}
    ).mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE_URL}/api/timerstate").mock(
        return_value=httpx.Response(
            200,
            json={
                "sessionId": None,
                "isRunning": False,
                "isBreak": False,
                "currentRound": 0,
                "timerModeId": 0,
            },
        )
    )
    respx.get(f"{BASE_URL}/api/sessions").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE_URL}/api/coursegoals").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE_URL}/api/metrics/summary").mock(
        return_value=httpx.Response(403, text="forbidden")
    )

    app = StudyLifeTUI()
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query_one("#timer-panel") is not None
        assert app.query_one("#hours-panel") is not None
        assert app.query_one("#next-session-panel") is not None
        assert app.query_one("#goals-panel") is not None
    app._client.close()


def test_app_raises_when_not_logged_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("studylife_cli.tui.load_credentials", lambda: None)
    with pytest.raises(SystemExit):
        StudyLifeTUI()
