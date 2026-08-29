"""Pydantic models mirroring StudyLife's actual OpenAPI schemas (fetched live from
`/openapi/v1.json` and cross-checked against StudyLife.Shared/Dtos.cs - not reconstructed from
memory, which previously produced wrong field names for StudySessionDto/CourseGoalDto).

Field names use snake_case here and are translated to/from the server's camelCase JSON via
StudyLifeModel's alias generator.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class StudyLifeModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Course(StudyLifeModel):
    id: int
    semester: int = 1
    name: str
    code: str = ""
    color: str = "#6C5CE7"
    icon: str = ""
    topics: list[str] = []
    ects: int = 5
    group: str | None = None


class Note(StudyLifeModel):
    id: int | None = None
    title: str
    content: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    course_id: int | None = None
    session_id: int | None = None
    is_markdown: bool = False
    source_url: str | None = None
    tags: str | None = None
    summary: str | None = None
    related_note_ids: list[int] = []


class Session(StudyLifeModel):
    id: int | None = None
    course_id: int
    # Ignored by the server for a brand-new session (re-derived from the resolved course) and
    # frozen/untouched for an existing one - only required to be non-empty by validation, its
    # actual content never matters once course_id is valid. See SessionsController.Validate.
    course_name: str = "-"
    course_color: str | None = None
    start_time: datetime
    end_time: datetime
    topic: str | None = None
    notes: str | None = None
    is_completed: bool = False
    timer_mode_id: int = 0
    recurrence_group_id: str | None = None


class CourseGoal(StudyLifeModel):
    course_id: int
    # Same "required non-empty, content ignored/frozen server-side" situation as
    # Session.course_name above - see CourseGoalsController.Save.
    course_name: str = "-"
    target_date: datetime | None = None
    completion_note: str | None = None
    completed_at: datetime | None = None
    grade: float | None = None
    completed_topics: str = ""
    tag: str | None = None


class TimerState(StudyLifeModel):
    session_id: int | None = None
    is_running: bool
    is_break: bool
    current_round: int
    timer_mode_id: int
    phase_ends_at: datetime | None = None
    updated_at: datetime | None = None
    server_now: datetime | None = None


class StudyProgramSummary(StudyLifeModel):
    id: int | None = None
    name: str
    is_built_in: bool
    is_completed: bool


class StudyProgramDetail(StudyLifeModel):
    id: int
    name: str
    group_ects_quotas: dict[str, int] = {}


class Webhook(StudyLifeModel):
    """studylife-webhooks' own WebhookOut shape (id is a string there, not an int) - the server's
    WebhooksProxyController is a pure, un-typed reverse proxy for this, so it never appears in
    StudyLife's own OpenAPI document."""

    id: str | None = None
    target_url: str
    events: list[str]
