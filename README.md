# studylife-cli

A command-line client for [StudyLife](https://github.com/lukislp/studylife), the self-hosted
study organizer. Manage notes, sessions, course goals, and webhooks from your terminal, get study
time reports and exports, or watch a live dashboard - scripts and shells welcome.

## Install

```bash
pip install studylife-cli
```

(or `pipx install studylife-cli` to keep it in its own isolated environment)

## Register the CLI on your instance

`studylife-cli` connects to your StudyLife instance through the same add-on mechanism any
third-party integration uses - there is no special-cased server support to set up. Register it
once via your own [studylife-developers](https://github.com/lukislp/studylife-developers) portal:

1. Open your `studylife-developers` instance and go to **Register new add-on**.
2. Fill in:
   - **Client ID**: `studylife-cli`
   - **Allowed redirect URIs** (one per line):
     ```
     http://127.0.0.1:8765/callback
     http://127.0.0.1:8766/callback
     http://127.0.0.1:8767/callback
     http://127.0.0.1:8768/callback
     ```
   - **Scopes**: whichever of notes/sessions/course-goals/timer/courses/study-programs/webhooks
     you want the CLI to be able to use.
3. Save.

## Log in

```bash
studylife login https://studylife.example.com
```

This opens your browser to approve the connection, then stores a scoped API key locally at
`~/.config/studylife-cli/credentials.json` (owner-readable only, on POSIX).

## Usage

```bash
studylife notes list
studylife notes search "exam"
studylife notes create "Title" "Content" --course-id 1

studylife sessions list
studylife sessions history --days 7
studylife sessions create 2026-08-30T14:00:00 --end 2026-08-30T15:00:00 --title "Focus block"

studylife goals list
studylife goals set 1 --target-ects 5
studylife goals due --within-days 14

studylife timer
studylife courses list
studylife programs list
studylife programs get 1

studylife webhooks list
studylife webhooks create https://example.com/hook session.completed
studylife webhooks delete 3

studylife report --period week
studylife export ./backup --notes-format markdown

studylife tui
```

Add `--json` to any command for machine-readable output:

```bash
studylife notes list --json | jq '.[] | .title'
```

- `studylife goals due` - open goals with an upcoming (or overdue) target date, soonest first.
- `studylife report` - study time by course for the past week or month, plus streak/ECTS
  progress if the "Read metrics summary" scope is granted.
- `studylife export` - back up notes, sessions, course goals, courses, and study programs to
  local files (`--notes-format json|markdown`), independent of your instance operator's own
  backups.
- `studylife tui` - a live terminal dashboard (today's study time, running timer, next session,
  open goals), auto-refreshing every 15s.

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## License

AGPL-3.0
