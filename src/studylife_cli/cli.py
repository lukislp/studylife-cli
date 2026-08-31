"""`studylife` - command-line client for a self-hosted StudyLife instance."""

from __future__ import annotations

import json as json_module
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from studylife_cli.client import ApiError, StudyLifeClient
from studylife_cli.credentials import Credentials, clear_credentials, load_credentials
from studylife_cli.login import DEFAULT_CLIENT_ID, LoginError, login_and_save
from studylife_cli.models import CourseGoal, Note, Session

app = typer.Typer(no_args_is_help=True, add_completion=False)
notes_app = typer.Typer(no_args_is_help=True, help="Manage notes.")
sessions_app = typer.Typer(no_args_is_help=True, help="Manage study sessions.")
goals_app = typer.Typer(no_args_is_help=True, help="Manage course goals.")
courses_app = typer.Typer(no_args_is_help=True, help="Browse courses.")
programs_app = typer.Typer(no_args_is_help=True, help="Browse study programs.")
webhooks_app = typer.Typer(no_args_is_help=True, help="Manage webhooks.")
app.add_typer(notes_app, name="notes")
app.add_typer(sessions_app, name="sessions")
app.add_typer(goals_app, name="goals")
app.add_typer(courses_app, name="courses")
app.add_typer(programs_app, name="programs")
app.add_typer(webhooks_app, name="webhooks")

# StudyLife content (course icons, note text) is arbitrary Unicode, but Python's stdout/stderr
# on Windows default to the console's legacy OEM/ANSI codepage (e.g. cp1252) unless overridden -
# printing anything outside that codepage then crashes the whole command with a
# UnicodeEncodeError instead of just rendering oddly. errors="replace" trades a perfect glyph
# for "never crashes on real StudyLife content" on whatever terminal this happens to run in.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")

# Also disables rich's separate "legacy Windows console" writer (a different code path, used on
# terminals it can't detect ANSI/VT support for), which encodes through the same codepage
# independently of sys.stdout and would otherwise still crash even with the reconfigure above.
console = Console(legacy_windows=False)
error_console = Console(stderr=True, legacy_windows=False)


@dataclass
class CliState:
    as_json: bool


# Click/Typer options declared on the root app's callback only parse when given BEFORE the
# subcommand (`studylife --json notes list`), not after (`studylife notes list --json`) - each
# subcommand has its own parser that doesn't know about the parent's options. Re-declaring the
# same flag on every leaf command and OR-ing it with the root-level one (see _use_json below)
# makes both orders work, matching how most people instinctively type it.
JSON_OPTION = typer.Option(False, "--json", help="Print machine-readable JSON instead of a table.")


def _use_json(ctx: typer.Context, local: bool) -> bool:
    state: CliState = ctx.obj
    return state.as_json or local


# Table-view field whitelists, one per resource type shown by a list/search/history command -
# the full field set (used unconditionally by --json) is often too wide for a terminal (a note's
# content, a session's course_color, a course's full topic list). Deliberately not applied to
# create/edit/delete confirmations (_confirm) or to single-item "get" views - those already show
# one thing at a time and benefit from seeing everything.
NOTE_TABLE_COLUMNS = ["id", "title", "course_id", "updated_at"]
SESSION_TABLE_COLUMNS = ["id", "course_name", "start_time", "end_time", "topic", "is_completed"]
COURSE_GOAL_TABLE_COLUMNS = ["course_id", "course_name", "target_date", "grade", "tag"]
COURSE_TABLE_COLUMNS = ["id", "name", "code", "semester", "ects"]


def _print_version_and_exit(value: bool) -> None:
    if not value:
        return
    from importlib.metadata import PackageNotFoundError, version

    try:
        console.print(version("studylife-cli"))
    except PackageNotFoundError:
        # Editable/uninstalled checkout (e.g. `uv run` before a build has ever run) - hatch-vcs
        # only writes package metadata as part of a real build/install, not on a bare source tree.
        console.print("unknown (not installed from a built package)")
    raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    as_json: bool = typer.Option(
        False, "--json", help="Print machine-readable JSON instead of a table."
    ),
    version: bool = typer.Option(
        False,
        "--version",
        callback=_print_version_and_exit,
        is_eager=True,
        help="Show the installed version and exit.",
    ),
) -> None:
    ctx.obj = CliState(as_json=as_json)


def _require_client(ctx: typer.Context) -> StudyLifeClient:
    credentials = load_credentials()
    if credentials is None:
        error_console.print(
            "Not logged in - run [bold]studylife login <instance-url>[/bold] first."
        )
        raise typer.Exit(1)
    return StudyLifeClient(credentials.instance_url, credentials.api_key)


def _print(
    as_json: bool, rows: list[dict[str, object]], title: str, columns: list[str] | None = None
) -> None:
    """columns restricts which fields the TABLE view shows (a resource can have far more fields
    than fit a terminal - e.g. a note's full content, or a session's course_color) - --json always
    returns every field regardless, since a table's readability limit doesn't apply there."""
    if as_json:
        # ensure_ascii=False - StudyLife content (course/note text) is mostly German;
        # json.dumps' own default escapes every non-ASCII character into a \uXXXX
        # sequence, technically valid JSON but unreadable for a human piping this to
        # a file or terminal.
        print(json_module.dumps(rows, indent=2, default=str, ensure_ascii=False))
        return
    if not rows:
        console.print(f"No {title.lower()}.")
        return
    display_rows = [{k: row.get(k) for k in columns} for row in rows] if columns else rows
    table = Table(title=title)
    for key in display_rows[0]:
        table.add_column(key)
    for row in display_rows:
        table.add_row(*(str(value) if value is not None else "" for value in row.values()))
    console.print(table)


def _confirm(as_json: bool, payload: dict[str, object], message: str) -> None:
    """Reports the outcome of a create/edit/delete command - the full affected resource (or, for
    a delete, just its id) as JSON with --json, otherwise the same short human message every
    mutation command already printed."""
    if as_json:
        print(json_module.dumps(payload, indent=2, default=str, ensure_ascii=False))
    else:
        console.print(message)


def _run(ctx: typer.Context, fn: object) -> object:
    """Calls fn() against a fresh client, translating ApiError/network failures into a clean
    exit instead of a raw traceback - the client is opened/closed per invocation since this is
    a short-lived CLI process, not a long-running one."""
    client = _require_client(ctx)
    try:
        return fn(client)
    except ApiError as exc:
        error_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    finally:
        client.close()


@app.command()
def login(
    instance_url: str = typer.Argument(
        ..., help="Base URL of your StudyLife instance, e.g. https://studylife.example.com"
    ),
    client_id: str = typer.Option(
        DEFAULT_CLIENT_ID, help="ClientId this CLI was registered under via studylife-developers."
    ),
) -> None:
    """Log in via your browser and store the resulting credential locally."""
    try:
        credentials: Credentials = login_and_save(instance_url, client_id=client_id)
    except LoginError as exc:
        error_console.print(f"[red]Login failed: {exc}[/red]")
        raise typer.Exit(1) from exc
    console.print(f"[green]Logged in[/green] to {credentials.instance_url}.")


@app.command()
def logout() -> None:
    """Remove the locally stored credential."""
    clear_credentials()
    console.print("Logged out.")


@app.command()
def whoami(ctx: typer.Context, as_json: bool = JSON_OPTION) -> None:
    """Show which StudyLife account and instance the stored credential belongs to."""
    result = _run(ctx, lambda c: c.whoami())
    credentials = load_credentials()
    payload = {
        "instance_url": credentials.instance_url if credentials else None,
        "user_id": result.user_id,
        "credential": result.credential,
    }
    _print(_use_json(ctx, as_json), [payload], "Whoami")


# -- Notes --------------------------------------------------------------------------


@notes_app.command("list")
def notes_list(ctx: typer.Context, as_json: bool = JSON_OPTION) -> None:
    """List notes. Table view shows a few fields - use --json for every field."""
    notes = _run(ctx, lambda c: c.list_notes())
    _print(
        _use_json(ctx, as_json),
        [n.model_dump(mode="json") for n in notes],
        "Notes",
        columns=NOTE_TABLE_COLUMNS,
    )


@notes_app.command("search")
def notes_search(ctx: typer.Context, query: str, as_json: bool = JSON_OPTION) -> None:
    """Search notes by title/content."""
    notes = _run(ctx, lambda c: c.search_notes(query))
    _print(
        _use_json(ctx, as_json),
        [n.model_dump(mode="json") for n in notes],
        "Notes",
        columns=NOTE_TABLE_COLUMNS,
    )


@notes_app.command("create")
def notes_create(
    ctx: typer.Context,
    title: str,
    content: str,
    course_id: int | None = typer.Option(None, help="Course to attach this note to."),
    as_json: bool = JSON_OPTION,
) -> None:
    """Create a note."""
    note = _run(
        ctx, lambda c: c.create_note(Note(title=title, content=content, course_id=course_id))
    )
    _confirm(_use_json(ctx, as_json), note.model_dump(mode="json"), f"Created note {note.id}.")


@notes_app.command("edit")
def notes_edit(
    ctx: typer.Context,
    note_id: int,
    title: str,
    content: str,
    course_id: int | None = typer.Option(None),
    as_json: bool = JSON_OPTION,
) -> None:
    """Edit a note. Replaces title/content/course_id entirely (not a partial patch)."""
    note = _run(
        ctx,
        lambda c: c.update_note(note_id, Note(title=title, content=content, course_id=course_id)),
    )
    _confirm(_use_json(ctx, as_json), note.model_dump(mode="json"), f"Updated note {note.id}.")


@notes_app.command("delete")
def notes_delete(ctx: typer.Context, note_id: int, as_json: bool = JSON_OPTION) -> None:
    """Delete a note."""
    _run(ctx, lambda c: c.delete_note(note_id))
    _confirm(_use_json(ctx, as_json), {"deleted": note_id}, f"Deleted note {note_id}.")


# -- Sessions -----------------------------------------------------------------------


@sessions_app.command("list")
def sessions_list(ctx: typer.Context, as_json: bool = JSON_OPTION) -> None:
    """List sessions. Unbounded - use `sessions history` for a long-term window."""
    sessions = _run(ctx, lambda c: c.list_sessions())
    _print(
        _use_json(ctx, as_json),
        [s.model_dump(mode="json") for s in sessions],
        "Sessions",
        columns=SESSION_TABLE_COLUMNS,
    )


@sessions_app.command("history")
def sessions_history(
    ctx: typer.Context,
    days: int | None = typer.Option(None),
    only_completed: bool | None = typer.Option(None, "--only-completed/--all"),
    as_json: bool = JSON_OPTION,
) -> None:
    """Long-term session history, default 1 year of completed sessions."""
    sessions = _run(ctx, lambda c: c.session_history(days=days, only_completed=only_completed))
    _print(
        _use_json(ctx, as_json),
        [s.model_dump(mode="json") for s in sessions],
        "Session history",
        columns=SESSION_TABLE_COLUMNS,
    )


@sessions_app.command("create")
def sessions_create(
    ctx: typer.Context,
    course_id: int = typer.Argument(..., help="Course id (see `studylife courses list`)."),
    start: str = typer.Argument(..., help="ISO 8601 start time, e.g. 2026-08-30T14:00:00"),
    end: str = typer.Argument(..., help="ISO 8601 end time, e.g. 2026-08-30T15:00:00"),
    topic: str | None = typer.Option(None),
    notes: str | None = typer.Option(None),
    completed: bool = typer.Option(False),
    as_json: bool = JSON_OPTION,
) -> None:
    """Create a study session."""
    session = _run(
        ctx,
        lambda c: c.create_session(
            Session(
                course_id=course_id,
                start_time=start,
                end_time=end,
                topic=topic,
                notes=notes,
                is_completed=completed,
            )
        ),
    )
    _confirm(
        _use_json(ctx, as_json), session.model_dump(mode="json"), f"Created session {session.id}."
    )


@sessions_app.command("edit")
def sessions_edit(
    ctx: typer.Context,
    session_id: int,
    course_id: int = typer.Argument(...),
    start: str = typer.Argument(...),
    end: str = typer.Argument(...),
    topic: str | None = typer.Option(None),
    notes: str | None = typer.Option(None),
    completed: bool = typer.Option(False),
    as_json: bool = JSON_OPTION,
) -> None:
    """Edit a session. Replaces every field entirely (not a partial patch)."""
    session = _run(
        ctx,
        lambda c: c.update_session(
            session_id,
            Session(
                course_id=course_id,
                start_time=start,
                end_time=end,
                topic=topic,
                notes=notes,
                is_completed=completed,
            ),
        ),
    )
    _confirm(
        _use_json(ctx, as_json), session.model_dump(mode="json"), f"Updated session {session.id}."
    )


@sessions_app.command("delete")
def sessions_delete(ctx: typer.Context, session_id: int, as_json: bool = JSON_OPTION) -> None:
    """Delete a session."""
    _run(ctx, lambda c: c.delete_session(session_id))
    _confirm(_use_json(ctx, as_json), {"deleted": session_id}, f"Deleted session {session_id}.")


# -- Course goals -------------------------------------------------------------------


@goals_app.command("list")
def goals_list(ctx: typer.Context, as_json: bool = JSON_OPTION) -> None:
    """List course goals."""
    goals = _run(ctx, lambda c: c.list_course_goals())
    _print(
        _use_json(ctx, as_json),
        [g.model_dump(mode="json") for g in goals],
        "Course goals",
        columns=COURSE_GOAL_TABLE_COLUMNS,
    )


@goals_app.command("set")
def goals_set(
    ctx: typer.Context,
    course_id: int,
    target_date: str | None = typer.Option(None, help="ISO 8601 date, e.g. 2026-12-31."),
    completion_note: str | None = typer.Option(None),
    completed_at: str | None = typer.Option(None, help="ISO 8601 date, once completed."),
    grade: float | None = typer.Option(None, help="German grading, 1.0 (best) to 5.0 (failed)."),
    completed_topics: str = typer.Option("", help="Comma-separated topic names."),
    tag: str | None = typer.Option(None),
    as_json: bool = JSON_OPTION,
) -> None:
    """Set (create or fully replace) the goal for a course. Every field not passed is cleared,
    not left as-is - this mirrors the server's own full-replace PUT semantics."""
    goal = _run(
        ctx,
        lambda c: c.save_course_goal(
            course_id,
            CourseGoal(
                course_id=course_id,
                target_date=target_date,
                completion_note=completion_note,
                completed_at=completed_at,
                grade=grade,
                completed_topics=completed_topics,
                tag=tag,
            ),
        ),
    )
    _confirm(
        _use_json(ctx, as_json),
        goal.model_dump(mode="json"),
        f"Saved goal for course {goal.course_id}.",
    )


@goals_app.command("delete")
def goals_delete(ctx: typer.Context, course_id: int, as_json: bool = JSON_OPTION) -> None:
    """Delete a course's goal."""
    _run(ctx, lambda c: c.delete_course_goal(course_id))
    _confirm(
        _use_json(ctx, as_json), {"deleted": course_id}, f"Deleted goal for course {course_id}."
    )


def _filter_due_goals(
    goals: list[CourseGoal], within_days: int, now: datetime | None = None
) -> list[CourseGoal]:
    """Open goals with a target_date at or before the cutoff, soonest (or most
    overdue) first. Skips goals with no target_date set at all - there's nothing to
    be "due" about - and already-completed ones. `now` is only ever overridden by
    tests, for a deterministic cutoff."""
    now = now or datetime.now()
    cutoff = now + timedelta(days=within_days)
    return sorted(
        (
            g
            for g in goals
            if g.target_date is not None and g.completed_at is None and g.target_date <= cutoff
        ),
        key=lambda g: g.target_date,
    )


@goals_app.command("due")
def goals_due(
    ctx: typer.Context,
    within_days: int = typer.Option(
        30, "--within-days", help="Only goals due within this many days from now."
    ),
    as_json: bool = JSON_OPTION,
) -> None:
    """Open goals with an upcoming (or overdue) target_date, soonest first."""
    goals = _run(ctx, lambda c: c.list_course_goals())
    due = _filter_due_goals(goals, within_days)
    _print(
        _use_json(ctx, as_json),
        [g.model_dump(mode="json") for g in due],
        f"Goals due within {within_days} days",
        columns=COURSE_GOAL_TABLE_COLUMNS,
    )


# -- Timer ----------------------------------------------------------------------------


@app.command()
def timer(ctx: typer.Context, as_json: bool = JSON_OPTION) -> None:
    """Show the current timer state."""
    state = _run(ctx, lambda c: c.get_timer_state())
    _print(_use_json(ctx, as_json), [state.model_dump(mode="json")], "Timer state")


@app.command()
def tui() -> None:
    """Live terminal dashboard - timer, today's/week's study time, next session,
    goals, and (with the 'Read metrics summary' scope granted) streak and ECTS
    progress. Press n to create a note, r to refresh, q to quit."""
    from studylife_cli.tui import run as run_tui

    run_tui()


# -- Courses / study programs --------------------------------------------------------


@courses_app.command("list")
def courses_list(ctx: typer.Context, as_json: bool = JSON_OPTION) -> None:
    """List courses in the active study program."""
    courses = _run(ctx, lambda c: c.list_courses())
    _print(
        _use_json(ctx, as_json),
        [c.model_dump(mode="json") for c in courses],
        "Courses",
        columns=COURSE_TABLE_COLUMNS,
    )


@programs_app.command("list")
def programs_list(ctx: typer.Context, as_json: bool = JSON_OPTION) -> None:
    """List study programs (built-in and custom)."""
    programs = _run(ctx, lambda c: c.list_study_programs())
    _print(_use_json(ctx, as_json), [p.model_dump(mode="json") for p in programs], "Study programs")


@programs_app.command("get")
def programs_get(ctx: typer.Context, program_id: int, as_json: bool = JSON_OPTION) -> None:
    """Get a custom study program's detail (course groups/ECTS quotas). Only applies to custom
    programs - the built-in program has no id and no detail endpoint."""
    program = _run(ctx, lambda c: c.get_study_program(program_id))
    _print(_use_json(ctx, as_json), [program.model_dump(mode="json")], "Study program")


# -- Webhooks ---------------------------------------------------------------------------


@webhooks_app.command("list")
def webhooks_list(ctx: typer.Context, as_json: bool = JSON_OPTION) -> None:
    """List registered webhooks."""
    webhooks = _run(ctx, lambda c: c.list_webhooks())
    _print(_use_json(ctx, as_json), [w.model_dump(mode="json") for w in webhooks], "Webhooks")


@webhooks_app.command("create")
def webhooks_create(
    ctx: typer.Context, target_url: str, events: list[str], as_json: bool = JSON_OPTION
) -> None:
    """Register a webhook. events is one or more event type names, e.g. session.completed."""
    webhook = _run(ctx, lambda c: c.create_webhook(target_url, events))
    _confirm(
        _use_json(ctx, as_json), webhook.model_dump(mode="json"), f"Created webhook {webhook.id}."
    )


@webhooks_app.command("delete")
def webhooks_delete(ctx: typer.Context, webhook_id: str, as_json: bool = JSON_OPTION) -> None:
    """Delete a webhook."""
    _run(ctx, lambda c: c.delete_webhook(webhook_id))
    _confirm(_use_json(ctx, as_json), {"deleted": webhook_id}, f"Deleted webhook {webhook_id}.")


# -- Export -----------------------------------------------------------------------------


def _slugify_note_filename(note: Note) -> str:
    """<id>-<slug>.md - the id prefix guarantees uniqueness (two notes can share a
    title), the slug keeps the filename human-readable. Non-alphanumeric characters
    become hyphens; StudyLife content is arbitrary Unicode (see the Windows-codepage
    comment near the top of this file), so this can't just assume ASCII."""
    slug = "".join(c if c.isalnum() else "-" for c in note.title.strip().lower())
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-") or "untitled"
    return f"{note.id}-{slug[:60]}.md"


def _write_notes_as_markdown(notes: list[Note], notes_dir: Path) -> None:
    notes_dir.mkdir(parents=True, exist_ok=True)
    for note in notes:
        front_matter = "\n".join(
            f"{key}: {value}"
            for key, value in {
                "title": note.title,
                "course_id": note.course_id,
                "created_at": note.created_at,
                "updated_at": note.updated_at,
                "tags": note.tags,
            }.items()
            if value is not None
        )
        content = f"---\n{front_matter}\n---\n\n{note.content}\n"
        (notes_dir / _slugify_note_filename(note)).write_text(content, encoding="utf-8")


def _write_json(resource_name: str, items: list[object], output_dir: Path) -> None:
    payload = [item.model_dump(mode="json") for item in items]  # type: ignore[attr-defined]
    # ensure_ascii=False - this is a personal backup meant to be human-readable if
    # someone opens it directly; json.dumps' own default escapes every non-ASCII
    # character into a \uXXXX sequence, which is valid JSON but unreadable for
    # course/note content that's mostly German.
    (output_dir / f"{resource_name}.json").write_text(
        json_module.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


@app.command()
def export(
    ctx: typer.Context,
    output_dir: Path = typer.Argument(
        ..., help="Directory to write the export into (created if it doesn't exist)."
    ),
    notes_format: str = typer.Option(
        "json",
        "--notes-format",
        help="'json' (default, one notes.json file) or 'markdown' (one .md file per "
        "note under output_dir/notes/, with a small frontmatter header).",
    ),
) -> None:
    """Export notes, sessions, course goals, courses, and study programs to local
    files - a personal backup independent of whatever backup strategy your StudyLife
    instance's operator runs. Every resource except notes is always written as JSON
    (they're structured data, not prose - markdown wouldn't add anything)."""
    if notes_format not in ("json", "markdown"):
        error_console.print("[red]--notes-format must be 'json' or 'markdown'.[/red]")
        raise typer.Exit(1)

    client = _require_client(ctx)
    try:
        notes = client.list_notes()
        sessions = client.list_sessions()
        goals = client.list_course_goals()
        courses = client.list_courses()
        programs = client.list_study_programs()
    except ApiError as exc:
        error_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    finally:
        client.close()

    output_dir.mkdir(parents=True, exist_ok=True)
    if notes_format == "markdown":
        _write_notes_as_markdown(notes, output_dir / "notes")
    else:
        _write_json("notes", notes, output_dir)
    _write_json("sessions", sessions, output_dir)
    _write_json("goals", goals, output_dir)
    _write_json("courses", courses, output_dir)
    _write_json("study_programs", programs, output_dir)

    console.print(
        f"Exported {len(notes)} notes, {len(sessions)} sessions, {len(goals)} goals, "
        f"{len(courses)} courses, and {len(programs)} study programs to {output_dir}."
    )


# -- Verb-first aliases --------------------------------------------------------------
#
# Every command above reads as "resource verb" (`studylife notes list`). Some people reach for
# "verb resource" instead (`studylife list notes`) - both are registered here for exactly the
# same underlying functions (a Typer @x.command() decorator hands back the plain function
# unchanged, so re-registering it under a second Typer app is just a second entry pointing at
# the same code, not a copy of it - no logic is duplicated, and a fix to one applies to both).
# Search/history/timer already read naturally as a bare verb (only one resource each supports
# them), so those get a single top-level command instead of a one-item dispatch group.
list_app = typer.Typer(
    no_args_is_help=True, help="List any resource (alias for `<resource> list`)."
)
create_app = typer.Typer(
    no_args_is_help=True, help="Create a resource (alias for `<resource> create`)."
)
edit_app = typer.Typer(no_args_is_help=True, help="Edit a resource (alias for `<resource> edit`).")
delete_app = typer.Typer(
    no_args_is_help=True, help="Delete a resource (alias for `<resource> delete`)."
)
get_app = typer.Typer(
    no_args_is_help=True, help="Get a single resource (alias for `<resource> get`)."
)
set_app = typer.Typer(no_args_is_help=True, help="Set a resource (alias for `<resource> set`).")

list_app.command("notes")(notes_list)
list_app.command("sessions")(sessions_list)
list_app.command("goals")(goals_list)
list_app.command("courses")(courses_list)
list_app.command("programs")(programs_list)
list_app.command("webhooks")(webhooks_list)
app.add_typer(list_app, name="list")

create_app.command("notes")(notes_create)
create_app.command("sessions")(sessions_create)
create_app.command("webhooks")(webhooks_create)
app.add_typer(create_app, name="create")

edit_app.command("notes")(notes_edit)
edit_app.command("sessions")(sessions_edit)
app.add_typer(edit_app, name="edit")

delete_app.command("notes")(notes_delete)
delete_app.command("sessions")(sessions_delete)
delete_app.command("goals")(goals_delete)
delete_app.command("webhooks")(webhooks_delete)
app.add_typer(delete_app, name="delete")

get_app.command("programs")(programs_get)
app.add_typer(get_app, name="get")

set_app.command("goals")(goals_set)
app.add_typer(set_app, name="set")

app.command("search")(notes_search)
app.command("history")(sessions_history)
app.command("due")(goals_due)


def run() -> None:
    app()


if __name__ == "__main__":
    sys.exit(run())
