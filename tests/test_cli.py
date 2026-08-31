"""Direct unit tests for cli.py's own pure helper logic - the Typer commands
themselves are thin wrappers around StudyLifeClient (already covered by
test_client.py) plus these, so testing the extracted logic directly is more
precise than driving the whole CLI through Typer's CliRunner for this.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from studylife_cli.cli import _filter_due_goals
from studylife_cli.models import CourseGoal

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
