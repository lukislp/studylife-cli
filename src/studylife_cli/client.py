"""Typed HTTP client for the StudyLife REST API, scoped to what
ApiKeyScopes.PubliclyGrantable actually allows a third-party client to do.

No internal-CA-trust handling here (unlike studylife-mcp's client.py) - this talks to the
instance's public-facing HTTPS endpoint, the same one a browser would use, so plain httpx
default TLS verification is enough.
"""

from __future__ import annotations

import httpx

from studylife_cli.models import (
    Course,
    CourseGoal,
    Note,
    Session,
    StudyProgramDetail,
    StudyProgramSummary,
    TimerState,
    Webhook,
    Whoami,
)


class ApiError(Exception):
    """Raised for any non-2xx response, carrying the status code and response body."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"StudyLife API returned {status_code}: {body.strip()}")
        self.status_code = status_code
        self.body = body


class StudyLifeClient:
    def __init__(self, instance_url: str, api_key: str, timeout: float = 15.0) -> None:
        self._http = httpx.Client(
            base_url=instance_url.rstrip("/"),
            headers={"X-Api-Key": api_key},
            timeout=timeout,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> StudyLifeClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def whoami(self) -> Whoami:
        return Whoami.model_validate(self._request("GET", "/api/auth/whoami").json())

    def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        response = self._http.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise ApiError(response.status_code, response.text)
        return response

    # -- Notes ------------------------------------------------------------------

    def list_notes(self) -> list[Note]:
        return [Note.model_validate(item) for item in self._request("GET", "/api/notes").json()]

    def search_notes(self, query: str) -> list[Note]:
        response = self._request("GET", "/api/notes/search", params={"q": query})
        return [Note.model_validate(item) for item in response.json()]

    def create_note(self, note: Note) -> Note:
        response = self._request(
            "POST",
            "/api/notes",
            json=note.model_dump(mode="json", by_alias=True, exclude_none=True),
        )
        return Note.model_validate(response.json())

    def update_note(self, note_id: int, note: Note) -> Note:
        response = self._request(
            "PUT",
            f"/api/notes/{note_id}",
            json=note.model_dump(mode="json", by_alias=True, exclude_none=True),
        )
        return Note.model_validate(response.json())

    def delete_note(self, note_id: int) -> None:
        self._request("DELETE", f"/api/notes/{note_id}")

    # -- Sessions -----------------------------------------------------------------

    def list_sessions(self) -> list[Session]:
        return [
            Session.model_validate(item) for item in self._request("GET", "/api/sessions").json()
        ]

    def session_history(
        self, days: int | None = None, only_completed: bool | None = None
    ) -> list[Session]:
        params: dict[str, object] = {}
        if days is not None:
            params["days"] = days
        if only_completed is not None:
            params["onlyCompleted"] = only_completed
        response = self._request("GET", "/api/sessions/history", params=params)
        return [Session.model_validate(item) for item in response.json()]

    def create_session(self, session: Session) -> Session:
        response = self._request(
            "POST",
            "/api/sessions",
            json=session.model_dump(mode="json", by_alias=True, exclude_none=True),
        )
        return Session.model_validate(response.json())

    def update_session(self, session_id: int, session: Session) -> Session:
        response = self._request(
            "PUT",
            f"/api/sessions/{session_id}",
            json=session.model_dump(mode="json", by_alias=True, exclude_none=True),
        )
        return Session.model_validate(response.json())

    def delete_session(self, session_id: int) -> None:
        self._request("DELETE", f"/api/sessions/{session_id}")

    # -- Course goals ---------------------------------------------------------------

    def list_course_goals(self) -> list[CourseGoal]:
        response = self._request("GET", "/api/coursegoals")
        return [CourseGoal.model_validate(item) for item in response.json()]

    def save_course_goal(self, course_id: int, goal: CourseGoal) -> CourseGoal:
        response = self._request(
            "PUT",
            f"/api/coursegoals/{course_id}",
            json=goal.model_dump(mode="json", by_alias=True, exclude_none=True),
        )
        return CourseGoal.model_validate(response.json())

    def delete_course_goal(self, course_id: int) -> None:
        self._request("DELETE", f"/api/coursegoals/{course_id}")

    # -- Timer / courses / study programs (read-only) -------------------------------

    def get_timer_state(self) -> TimerState:
        return TimerState.model_validate(self._request("GET", "/api/timerstate").json())

    def list_courses(self) -> list[Course]:
        return [Course.model_validate(item) for item in self._request("GET", "/api/courses").json()]

    def list_study_programs(self) -> list[StudyProgramSummary]:
        response = self._request("GET", "/api/studyprograms")
        return [StudyProgramSummary.model_validate(item) for item in response.json()]

    def get_study_program(self, program_id: int) -> StudyProgramDetail:
        response = self._request("GET", f"/api/studyprograms/{program_id}")
        return StudyProgramDetail.model_validate(response.json())

    # -- Webhooks -------------------------------------------------------------------

    def list_webhooks(self) -> list[Webhook]:
        return [
            Webhook.model_validate(item) for item in self._request("GET", "/api/webhooks").json()
        ]

    def create_webhook(self, target_url: str, events: list[str]) -> Webhook:
        response = self._request(
            "POST", "/api/webhooks", json={"targetUrl": target_url, "events": events}
        )
        return Webhook.model_validate(response.json())

    def delete_webhook(self, webhook_id: str) -> None:
        self._request("DELETE", f"/api/webhooks/{webhook_id}")
