"""`studylife tui` - a live terminal dashboard, built on Textual.

StudyLifeClient is synchronous (plain httpx.Client, shared with the rest of this CLI) -
Textual's own event loop is asyncio-based and would stall on every blocking HTTP round
trip, so every client call here runs in a background thread via @work(thread=True) and
hands its result back to the UI thread through call_from_thread, the pattern Textual's
own docs recommend for wrapping a synchronous library.

Metrics.GetSummary (streak, ECTS progress, week/month hours) was only added to
ApiKeyScopes.PubliclyGrantable after this client's scope set was first settled - an
installation registered before that (or one that just didn't grant it) gets ApiError(403)
here, handled as a soft, expected case: those panels show a hint to grant the scope
instead of crashing the whole dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Grid, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Label, Static

from studylife_cli.client import ApiError, StudyLifeClient
from studylife_cli.credentials import load_credentials
from studylife_cli.models import Note, Session, TimerState

REFRESH_INTERVAL_SECONDS = 15.0

_PANEL_IDS = ("#timer-panel", "#hours-panel", "#next-session-panel", "#goals-panel")


def _sum_session_minutes(sessions: list[Session]) -> int:
    """Mirrors studylife-alexa's own _sum_session_minutes (handlers.py) - clamps an
    in-progress session's end to "now" so it counts elapsed time so far, not its full
    (partly still in the future) scheduled duration."""
    now = datetime.now()
    total_seconds = 0.0
    for session in sessions:
        end = min(session.end_time, now)
        total_seconds += max(0.0, (end - session.start_time).total_seconds())
    return int(total_seconds // 60)


def _next_upcoming_session(sessions: list[Session]) -> Session | None:
    now = datetime.now()
    upcoming = [s for s in sessions if s.start_time > now]
    return min(upcoming, key=lambda s: s.start_time) if upcoming else None


def _format_duration(total_minutes: int) -> str:
    if total_minutes < 60:
        return f"{total_minutes}m"
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h {minutes}m" if minutes else f"{hours}h"


@dataclass
class DashboardStats:
    today_minutes: int
    timer: TimerState
    next_session: Session | None
    open_goals: int
    total_goals: int
    metrics_available: bool
    streak_current: int = 0
    week_hours: float = 0.0
    month_hours: float = 0.0
    ects_earned: int = 0
    ects_total: int = 0
    program_name: str = ""


def load_stats(client: StudyLifeClient) -> DashboardStats:
    """All the blocking calls a dashboard refresh needs, gathered into one call so
    _fetch_stats below has exactly one thing to run in its worker thread."""
    today_sessions = client.session_history(days=1, only_completed=False)
    timer = client.get_timer_state()
    all_sessions = client.list_sessions()
    goals = client.list_course_goals()

    stats = DashboardStats(
        today_minutes=_sum_session_minutes(today_sessions),
        timer=timer,
        next_session=_next_upcoming_session(all_sessions),
        open_goals=sum(1 for g in goals if g.completed_at is None),
        total_goals=len(goals),
        metrics_available=False,
    )

    try:
        summary = client.get_metrics_summary()
    except ApiError:
        return stats

    stats.metrics_available = True
    stats.streak_current = summary.streak.current
    stats.week_hours = summary.hours.week
    stats.month_hours = summary.hours.month
    stats.ects_earned = summary.ects.earned
    stats.ects_total = summary.ects.total
    stats.program_name = summary.program.name
    return stats


class CreateNoteScreen(ModalScreen[tuple[str, str] | None]):
    """`n` opens this - title + content, Enter on either field submits, Escape cancels."""

    DEFAULT_CSS = """
    CreateNoteScreen { align: center middle; }
    #dialog { width: 60; padding: 1 2; border: round $accent; background: $surface; }
    #dialog Input { margin-top: 1; }
    """

    BINDINGS: ClassVar = [("escape", "dismiss(None)", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label("New note (Enter to save, Esc to cancel)")
            yield Input(placeholder="Title", id="title")
            yield Input(placeholder="Content", id="content")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        title = self.query_one("#title", Input).value.strip()
        content = self.query_one("#content", Input).value.strip()
        if title and content:
            self.dismiss((title, content))


class StudyLifeTUI(App[None]):
    TITLE = "StudyLife"
    CSS = """
    Screen { background: $background; }
    #stats { grid-size: 2; grid-gutter: 1 2; padding: 1 2; }
    .panel { border: round $accent; padding: 1 2; height: 100%; }
    """
    BINDINGS: ClassVar = [
        ("r", "refresh", "Refresh"),
        ("n", "new_note", "New note"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        credentials = load_credentials()
        if credentials is None:
            raise SystemExit("Not logged in - run `studylife login <instance-url>` first.")
        self._client = StudyLifeClient(credentials.instance_url, credentials.api_key)
        self._instance_url = credentials.instance_url

    def compose(self) -> ComposeResult:
        yield Header()
        with Grid(id="stats"):
            yield Static("Loading...", id="timer-panel", classes="panel")
            yield Static("Loading...", id="hours-panel", classes="panel")
            yield Static("Loading...", id="next-session-panel", classes="panel")
            yield Static("Loading...", id="goals-panel", classes="panel")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = self._instance_url
        self.action_refresh()
        self.set_interval(REFRESH_INTERVAL_SECONDS, self.action_refresh)

    def on_unmount(self) -> None:
        self._client.close()

    def action_refresh(self) -> None:
        self._fetch_stats()

    @work(thread=True, exclusive=True)
    def _fetch_stats(self) -> None:
        try:
            stats = load_stats(self._client)
        except ApiError as exc:
            self.call_from_thread(self._show_error, str(exc))
            return
        self.call_from_thread(self._apply_stats, stats)

    def _show_error(self, message: str) -> None:
        for panel_id in _PANEL_IDS:
            self.query_one(panel_id, Static).update(f"[red]{message}[/red]")

    def _apply_stats(self, stats: DashboardStats) -> None:
        timer = stats.timer
        if not timer.is_running:
            timer_text = "Not running"
        elif timer.is_break:
            timer_text = "Running - on a break"
        else:
            timer_text = "Running"
        self.query_one("#timer-panel", Static).update(f"[b]Focus timer[/b]\n{timer_text}")

        hours_lines = [f"Today: {_format_duration(stats.today_minutes)}"]
        if stats.metrics_available:
            hours_lines.append(f"This week: {stats.week_hours:.1f}h")
            hours_lines.append(f"This month: {stats.month_hours:.1f}h")
            hours_lines.append(f"Streak: {stats.streak_current} days")
        else:
            hours_lines.append("[dim]Grant 'Read metrics summary' for more[/dim]")
        self.query_one("#hours-panel", Static).update(
            "[b]Study time[/b]\n" + "\n".join(hours_lines)
        )

        if stats.next_session is not None:
            session = stats.next_session
            next_text = f"{session.start_time:%a %H:%M} - {session.course_name}"
        else:
            next_text = "Nothing scheduled"
        self.query_one("#next-session-panel", Static).update(f"[b]Next session[/b]\n{next_text}")

        goals_lines = [f"{stats.open_goals} of {stats.total_goals} open"]
        if stats.metrics_available and stats.ects_total:
            goals_lines.append(f"{stats.program_name}: {stats.ects_earned}/{stats.ects_total} ECTS")
        self.query_one("#goals-panel", Static).update("[b]Goals[/b]\n" + "\n".join(goals_lines))

    def action_new_note(self) -> None:
        def handle_result(result: tuple[str, str] | None) -> None:
            if result is None:
                return
            title, content = result
            self._create_note(title, content)

        self.push_screen(CreateNoteScreen(), handle_result)

    @work(thread=True)
    def _create_note(self, title: str, content: str) -> None:
        try:
            self._client.create_note(Note(title=title, content=content))
        except ApiError as exc:
            self.call_from_thread(self.notify, str(exc), severity="error")
        else:
            self.call_from_thread(self.notify, f"Note '{title}' saved.")


def run() -> None:
    StudyLifeTUI().run()
