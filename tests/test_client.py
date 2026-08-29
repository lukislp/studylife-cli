from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
import respx

from studylife_cli.client import ApiError, StudyLifeClient
from studylife_cli.models import CourseGoal, Note, Session, Webhook

BASE_URL = "https://studylife.example.com"


@pytest.fixture
def client() -> Iterator[StudyLifeClient]:
    with StudyLifeClient(BASE_URL, api_key="test-key") as c:
        yield c


@respx.mock
def test_list_notes_sends_api_key_header(client: StudyLifeClient) -> None:
    route = respx.get(f"{BASE_URL}/api/notes").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "title": "t", "content": "c"}])
    )
    notes = client.list_notes()
    assert route.called
    assert route.calls.last.request.headers["x-api-key"] == "test-key"
    assert notes == [Note(id=1, title="t", content="c")]


@respx.mock
def test_search_notes(client: StudyLifeClient) -> None:
    respx.get(f"{BASE_URL}/api/notes/search", params={"q": "exam"}).mock(
        return_value=httpx.Response(200, json=[{"id": 2, "title": "exam prep", "content": "..."}])
    )
    notes = client.search_notes("exam")
    assert notes[0].title == "exam prep"


@respx.mock
def test_create_note(client: StudyLifeClient) -> None:
    respx.post(f"{BASE_URL}/api/notes").mock(
        return_value=httpx.Response(201, json={"id": 3, "title": "new", "content": "body"})
    )
    note = client.create_note(Note(title="new", content="body"))
    assert note.id == 3


@respx.mock
def test_delete_note(client: StudyLifeClient) -> None:
    route = respx.delete(f"{BASE_URL}/api/notes/5").mock(return_value=httpx.Response(204))
    client.delete_note(5)
    assert route.called


@respx.mock
def test_api_error_raised_on_4xx(client: StudyLifeClient) -> None:
    respx.get(f"{BASE_URL}/api/notes").mock(return_value=httpx.Response(401, text="unauthorized"))
    with pytest.raises(ApiError) as exc_info:
        client.list_notes()
    assert exc_info.value.status_code == 401


@respx.mock
def test_api_error_raised_on_403_forbidden_scope(client: StudyLifeClient) -> None:
    respx.post(f"{BASE_URL}/api/webhooks").mock(
        return_value=httpx.Response(403, text="missing scope")
    )
    with pytest.raises(ApiError) as exc_info:
        client.create_webhook("https://example.com/hook", ["session.completed"])
    assert exc_info.value.status_code == 403


@respx.mock
def test_list_sessions(client: StudyLifeClient) -> None:
    respx.get(f"{BASE_URL}/api/sessions").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "courseId": 1,
                    "courseName": "Math",
                    "courseColor": "#000000",
                    "startTime": "2026-08-30T10:00:00",
                    "endTime": "2026-08-30T11:00:00",
                    "isCompleted": False,
                    "timerModeId": 0,
                }
            ],
        )
    )
    sessions = client.list_sessions()
    assert isinstance(sessions[0], Session)


@respx.mock
def test_session_history_forwards_query_params(client: StudyLifeClient) -> None:
    route = respx.get(
        f"{BASE_URL}/api/sessions/history", params={"days": "7", "onlyCompleted": "true"}
    ).mock(return_value=httpx.Response(200, json=[]))
    client.session_history(days=7, only_completed=True)
    assert route.called


@respx.mock
def test_course_goal_round_trip(client: StudyLifeClient) -> None:
    respx.put(f"{BASE_URL}/api/coursegoals/1").mock(
        return_value=httpx.Response(
            200, json={"courseId": 1, "courseName": "Math", "grade": 1.3, "completedTopics": ""}
        )
    )
    goal = client.save_course_goal(1, CourseGoal(course_id=1, grade=1.3))
    assert goal.grade == 1.3


@respx.mock
def test_list_webhooks(client: StudyLifeClient) -> None:
    respx.get(f"{BASE_URL}/api/webhooks").mock(
        return_value=httpx.Response(
            200, json=[{"id": "abc123", "targetUrl": "https://x", "events": ["a"]}]
        )
    )
    webhooks = client.list_webhooks()
    assert webhooks == [Webhook(id="abc123", target_url="https://x", events=["a"])]


@respx.mock
def test_delete_webhook_accepts_string_id(client: StudyLifeClient) -> None:
    route = respx.delete(f"{BASE_URL}/api/webhooks/abc123").mock(return_value=httpx.Response(204))
    client.delete_webhook("abc123")
    assert route.called
