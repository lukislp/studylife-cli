"""`studylife` - command-line client for a self-hosted StudyLife instance."""

from __future__ import annotations

import json as json_module
import sys
from dataclasses import dataclass

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


def _print(ctx: typer.Context, rows: list[dict[str, object]], title: str) -> None:
    state: CliState = ctx.obj
    if state.as_json:
        print(json_module.dumps(rows, indent=2, default=str))
        return
    if not rows:
        console.print(f"No {title.lower()}.")
        return
    table = Table(title=title)
    for key in rows[0]:
        table.add_column(key)
    for row in rows:
        table.add_row(*(str(value) if value is not None else "" for value in row.values()))
    console.print(table)


def _confirm(ctx: typer.Context, payload: dict[str, object], message: str) -> None:
    """Reports the outcome of a create/edit/delete command - the full affected resource (or, for
    a delete, just its id) as JSON with --json, otherwise the same short human message every
    mutation command already printed."""
    state: CliState = ctx.obj
    if state.as_json:
        print(json_module.dumps(payload, indent=2, default=str))
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


# -- Notes --------------------------------------------------------------------------


@notes_app.command("list")
def notes_list(ctx: typer.Context) -> None:
    notes = _run(ctx, lambda c: c.list_notes())
    _print(ctx, [n.model_dump(mode="json") for n in notes], "Notes")


@notes_app.command("search")
def notes_search(ctx: typer.Context, query: str) -> None:
    notes = _run(ctx, lambda c: c.search_notes(query))
    _print(ctx, [n.model_dump(mode="json") for n in notes], "Notes")


@notes_app.command("create")
def notes_create(
    ctx: typer.Context,
    title: str,
    content: str,
    course_id: int | None = typer.Option(None, help="Course to attach this note to."),
) -> None:
    note = _run(
        ctx, lambda c: c.create_note(Note(title=title, content=content, course_id=course_id))
    )
    _confirm(ctx, note.model_dump(mode="json"), f"Created note {note.id}.")


@notes_app.command("edit")
def notes_edit(
    ctx: typer.Context,
    note_id: int,
    title: str,
    content: str,
    course_id: int | None = typer.Option(None),
) -> None:
    note = _run(
        ctx,
        lambda c: c.update_note(note_id, Note(title=title, content=content, course_id=course_id)),
    )
    _confirm(ctx, note.model_dump(mode="json"), f"Updated note {note.id}.")


@notes_app.command("delete")
def notes_delete(ctx: typer.Context, note_id: int) -> None:
    _run(ctx, lambda c: c.delete_note(note_id))
    _confirm(ctx, {"deleted": note_id}, f"Deleted note {note_id}.")


# -- Sessions -----------------------------------------------------------------------


@sessions_app.command("list")
def sessions_list(ctx: typer.Context) -> None:
    sessions = _run(ctx, lambda c: c.list_sessions())
    _print(ctx, [s.model_dump(mode="json") for s in sessions], "Sessions")


@sessions_app.command("history")
def sessions_history(
    ctx: typer.Context,
    days: int | None = typer.Option(None),
    only_completed: bool | None = typer.Option(None, "--only-completed/--all"),
) -> None:
    sessions = _run(ctx, lambda c: c.session_history(days=days, only_completed=only_completed))
    _print(ctx, [s.model_dump(mode="json") for s in sessions], "Session history")


@sessions_app.command("create")
def sessions_create(
    ctx: typer.Context,
    course_id: int = typer.Argument(..., help="Course id (see `studylife courses list`)."),
    start: str = typer.Argument(..., help="ISO 8601 start time, e.g. 2026-08-30T14:00:00"),
    end: str = typer.Argument(..., help="ISO 8601 end time, e.g. 2026-08-30T15:00:00"),
    topic: str | None = typer.Option(None),
    notes: str | None = typer.Option(None),
    completed: bool = typer.Option(False),
) -> None:
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
    _confirm(ctx, session.model_dump(mode="json"), f"Created session {session.id}.")


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
) -> None:
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
    _confirm(ctx, session.model_dump(mode="json"), f"Updated session {session.id}.")


@sessions_app.command("delete")
def sessions_delete(ctx: typer.Context, session_id: int) -> None:
    _run(ctx, lambda c: c.delete_session(session_id))
    _confirm(ctx, {"deleted": session_id}, f"Deleted session {session_id}.")


# -- Course goals -------------------------------------------------------------------


@goals_app.command("list")
def goals_list(ctx: typer.Context) -> None:
    goals = _run(ctx, lambda c: c.list_course_goals())
    _print(ctx, [g.model_dump(mode="json") for g in goals], "Course goals")


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
) -> None:
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
    _confirm(ctx, goal.model_dump(mode="json"), f"Saved goal for course {goal.course_id}.")


@goals_app.command("delete")
def goals_delete(ctx: typer.Context, course_id: int) -> None:
    _run(ctx, lambda c: c.delete_course_goal(course_id))
    _confirm(ctx, {"deleted": course_id}, f"Deleted goal for course {course_id}.")


# -- Timer ----------------------------------------------------------------------------


@app.command()
def timer(ctx: typer.Context) -> None:
    """Show the current timer state."""
    state = _run(ctx, lambda c: c.get_timer_state())
    _print(ctx, [state.model_dump(mode="json")], "Timer state")


# -- Courses / study programs --------------------------------------------------------


@courses_app.command("list")
def courses_list(ctx: typer.Context) -> None:
    courses = _run(ctx, lambda c: c.list_courses())
    _print(ctx, [c.model_dump(mode="json") for c in courses], "Courses")


@programs_app.command("list")
def programs_list(ctx: typer.Context) -> None:
    programs = _run(ctx, lambda c: c.list_study_programs())
    _print(ctx, [p.model_dump(mode="json") for p in programs], "Study programs")


@programs_app.command("get")
def programs_get(ctx: typer.Context, program_id: int) -> None:
    program = _run(ctx, lambda c: c.get_study_program(program_id))
    _print(ctx, [program.model_dump(mode="json")], "Study program")


# -- Webhooks ---------------------------------------------------------------------------


@webhooks_app.command("list")
def webhooks_list(ctx: typer.Context) -> None:
    webhooks = _run(ctx, lambda c: c.list_webhooks())
    _print(ctx, [w.model_dump(mode="json") for w in webhooks], "Webhooks")


@webhooks_app.command("create")
def webhooks_create(ctx: typer.Context, target_url: str, events: list[str]) -> None:
    webhook = _run(ctx, lambda c: c.create_webhook(target_url, events))
    _confirm(ctx, webhook.model_dump(mode="json"), f"Created webhook {webhook.id}.")


@webhooks_app.command("delete")
def webhooks_delete(ctx: typer.Context, webhook_id: str) -> None:
    _run(ctx, lambda c: c.delete_webhook(webhook_id))
    _confirm(ctx, {"deleted": webhook_id}, f"Deleted webhook {webhook_id}.")


def run() -> None:
    app()


if __name__ == "__main__":
    sys.exit(run())
