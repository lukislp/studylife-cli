"""Direct unit tests for cli.py's own pure helper logic - the Typer commands
themselves are thin wrappers around StudyLifeClient (already covered by
test_client.py) plus these, so testing the extracted logic directly is more
precise than driving the whole CLI through Typer's CliRunner for most of it. A
few full CliRunner tests cover the `export`/`report` commands' actual wiring
end to end.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import respx
from typer.testing import CliRunner

from studylife_cli import cli
from studylife_cli.cli import (
    _build_course_breakdown,
    _filter_due_goals,
    _report_format_duration,
    _slugify_note_filename,
    _write_json,
    _write_notes_as_markdown,
)
from studylife_cli.credentials import Credentials
from studylife_cli.models import CourseGoal, Note, Session

BASE_URL = "https://studylife.example.com"

runner = CliRunner()

NOW = datetime(2026, 8, 31, 12, 0, 0)


def _goal(
    course_id: int, target_date: datetime | None, completed_at: datetime | None = None
) -> CourseGoal:
    return CourseGoal(course_id=course_id, target_date=target_date, completed_at=completed_at)


def test_filter_due_goals_includes_upcoming_within_window() -> None:
    goal = _goal(1, NOW + timedelta(days=10))
    assert _filter_due_goals([goal], within_days=30, now=NOW) == [goal]


def test_filter_due_goals_excludes_beyond_window() -> None:
    goal = _goal(1, NOW + timedelta(days=60))
    assert _filter_due_goals([goal], within_days=30, now=NOW) == []


def test_filter_due_goals_includes_overdue() -> None:
    """An overdue, still-open goal is arguably the most urgent thing to surface -
    must not be silently excluded just because its target_date is in the past."""
    goal = _goal(1, NOW - timedelta(days=5))
    assert _filter_due_goals([goal], within_days=30, now=NOW) == [goal]


def test_filter_due_goals_excludes_completed() -> None:
    goal = _goal(1, NOW + timedelta(days=5), completed_at=NOW - timedelta(days=1))
    assert _filter_due_goals([goal], within_days=30, now=NOW) == []


def test_filter_due_goals_excludes_no_target_date() -> None:
    goal = _goal(1, None)
    assert _filter_due_goals([goal], within_days=30, now=NOW) == []


def test_filter_due_goals_sorts_most_overdue_first() -> None:
    soon = _goal(1, NOW + timedelta(days=5))
    overdue = _goal(2, NOW - timedelta(days=10))
    later = _goal(3, NOW + timedelta(days=20))

    result = _filter_due_goals([soon, overdue, later], within_days=30, now=NOW)

    assert [g.course_id for g in result] == [2, 1, 3]


def test_slugify_note_filename_basic() -> None:
    note = Note(id=7, title="Exam Prep", content="")
    assert _slugify_note_filename(note) == "7-exam-prep.md"


def test_slugify_note_filename_special_characters_become_hyphens() -> None:
    note = Note(id=1, title="Q&A: Chapter 3 (final)!", content="")
    assert _slugify_note_filename(note) == "1-q-a-chapter-3-final.md"


def test_slugify_note_filename_empty_title_falls_back() -> None:
    note = Note(id=2, title="   ", content="")
    assert _slugify_note_filename(note) == "2-untitled.md"


def test_slugify_note_filename_truncates_long_titles() -> None:
    note = Note(id=3, title="x" * 200, content="")
    filename = _slugify_note_filename(note)
    assert filename == f"3-{'x' * 60}.md"


def test_write_notes_as_markdown_includes_frontmatter_and_content(tmp_path: Path) -> None:
    note = Note(id=1, title="My Note", content="the body", course_id=5)
    _write_notes_as_markdown([note], tmp_path / "notes")

    written = (tmp_path / "notes" / "1-my-note.md").read_text(encoding="utf-8")
    assert "title: My Note" in written
    assert "course_id: 5" in written
    assert "the body" in written


def test_write_json_dumps_model_list(tmp_path: Path) -> None:
    notes = [Note(id=1, title="A", content="a"), Note(id=2, title="B", content="b")]
    _write_json("notes", notes, tmp_path)

    data = json.loads((tmp_path / "notes.json").read_text(encoding="utf-8"))
    assert [item["title"] for item in data] == ["A", "B"]


@respx.mock
def test_export_command_writes_all_resources_as_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "load_credentials",
        lambda: Credentials(instance_url=BASE_URL, client_id="studylife-cli", api_key="k"),
    )
    respx.get(f"{BASE_URL}/api/notes").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "title": "n", "content": "c"}])
    )
    respx.get(f"{BASE_URL}/api/sessions").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE_URL}/api/coursegoals").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE_URL}/api/courses").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE_URL}/api/studyprograms").mock(return_value=httpx.Response(200, json=[]))

    output_dir = tmp_path / "backup"
    result = runner.invoke(cli.app, ["export", str(output_dir)])

    assert result.exit_code == 0, result.output
    assert "Exported 1 notes" in result.output
    assert (output_dir / "notes.json").exists()
    assert (output_dir / "sessions.json").exists()
    assert (output_dir / "goals.json").exists()
    assert (output_dir / "courses.json").exists()
    assert (output_dir / "study_programs.json").exists()


@respx.mock
def test_export_command_markdown_notes_format(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "load_credentials",
        lambda: Credentials(instance_url=BASE_URL, client_id="studylife-cli", api_key="k"),
    )
    respx.get(f"{BASE_URL}/api/notes").mock(
        return_value=httpx.Response(200, json=[{"id": 1, "title": "My Note", "content": "body"}])
    )
    respx.get(f"{BASE_URL}/api/sessions").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE_URL}/api/coursegoals").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE_URL}/api/courses").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE_URL}/api/studyprograms").mock(return_value=httpx.Response(200, json=[]))

    output_dir = tmp_path / "backup"
    result = runner.invoke(cli.app, ["export", str(output_dir), "--notes-format", "markdown"])

    assert result.exit_code == 0, result.output
    assert (output_dir / "notes" / "1-my-note.md").exists()
    assert not (output_dir / "notes.json").exists()
    # Everything else is unaffected by --notes-format.
    assert (output_dir / "sessions.json").exists()


def test_export_command_rejects_invalid_notes_format(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "load_credentials",
        lambda: Credentials(instance_url=BASE_URL, client_id="studylife-cli", api_key="k"),
    )
    result = runner.invoke(cli.app, ["export", str(tmp_path / "backup"), "--notes-format", "yaml"])
    assert result.exit_code == 1


def _session(
    course_id: int, course_name: str, start: datetime, end: datetime, session_id: int = 1
) -> Session:
    return Session(
        id=session_id, course_id=course_id, course_name=course_name, start_time=start, end_time=end
    )


def test_report_format_duration_minutes_only() -> None:
    assert _report_format_duration(45) == "45m"


def test_report_format_duration_hours_and_minutes() -> None:
    assert _report_format_duration(90) == "1h 30m"


def test_build_course_breakdown_groups_and_sums_by_course() -> None:
    sessions = [
        _session(1, "Math", NOW - timedelta(hours=3), NOW - timedelta(hours=2), session_id=1),
        _session(1, "Math", NOW - timedelta(hours=1, minutes=30), NOW - timedelta(hours=1), 2),
        _session(2, "AI", NOW - timedelta(hours=5), NOW - timedelta(hours=4), 3),
    ]

    breakdown = _build_course_breakdown(sessions, now=NOW)

    by_course = {line.course_id: line for line in breakdown}
    assert by_course[1].minutes == 90
    assert by_course[1].session_count == 2
    assert by_course[2].minutes == 60
    assert by_course[2].session_count == 1


def test_build_course_breakdown_sorted_by_minutes_descending() -> None:
    sessions = [
        _session(1, "Small", NOW - timedelta(minutes=30), NOW, 1),
        _session(2, "Big", NOW - timedelta(hours=3), NOW, 2),
    ]

    breakdown = _build_course_breakdown(sessions, now=NOW)

    assert [line.course_id for line in breakdown] == [2, 1]


def test_build_course_breakdown_clamps_in_progress_session_to_now() -> None:
    """Regression (mirrors studylife-alexa's/studylife tui's own fix): a session
    fetched with only_completed=False can have an end_time in the future (still
    running) - must count elapsed time so far, not the full scheduled duration."""
    sessions = [_session(1, "AI", NOW - timedelta(hours=2), NOW + timedelta(hours=3), 1)]

    breakdown = _build_course_breakdown(sessions, now=NOW)

    assert breakdown[0].minutes == 120


def test_build_course_breakdown_excludes_not_yet_started_session() -> None:
    sessions = [_session(1, "AI", NOW + timedelta(hours=1), NOW + timedelta(hours=2), 1)]
    assert _build_course_breakdown(sessions, now=NOW) == []


@respx.mock
def test_report_command_prints_table(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "load_credentials",
        lambda: Credentials(instance_url=BASE_URL, client_id="studylife-cli", api_key="k"),
    )
    respx.get(
        f"{BASE_URL}/api/sessions/history", params={"days": "7", "onlyCompleted": "false"}
    ).mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 1,
                    "courseId": 1,
                    "courseName": "Math",
                    "startTime": "2026-08-30T10:00:00",
                    "endTime": "2026-08-30T11:00:00",
                }
            ],
        )
    )
    respx.get(f"{BASE_URL}/api/metrics/summary").mock(
        return_value=httpx.Response(403, text="forbidden")
    )

    result = runner.invoke(cli.app, ["report"])

    assert result.exit_code == 0, result.output
    assert "Total study time" in result.output
    assert "Math" in result.output
    assert "Grant the 'Read metrics summary' scope" in result.output


@respx.mock
def test_report_command_json_output(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "load_credentials",
        lambda: Credentials(instance_url=BASE_URL, client_id="studylife-cli", api_key="k"),
    )
    respx.get(
        f"{BASE_URL}/api/sessions/history", params={"days": "30", "onlyCompleted": "false"}
    ).mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE_URL}/api/metrics/summary").mock(
        return_value=httpx.Response(
            200,
            json={
                "asOf": "2026-08-31T12:00:00",
                "program": {"id": None, "name": "Applied AI", "isBuiltIn": True},
                "streak": {"current": 3, "longest": 5},
                "hours": {"week": 1.0, "month": 4.0, "total": 10.0, "totalSessions": 5},
                "ects": {"earned": 20, "total": 180},
            },
        )
    )

    result = runner.invoke(cli.app, ["report", "--period", "month", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["period"] == "month"
    assert payload["metrics_available"] is True
    assert payload["streak_current"] == 3
    assert payload["ects_total"] == 180


def test_report_command_rejects_invalid_period(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "load_credentials",
        lambda: Credentials(instance_url=BASE_URL, client_id="studylife-cli", api_key="k"),
    )
    result = runner.invoke(cli.app, ["report", "--period", "year"])
    assert result.exit_code == 1
