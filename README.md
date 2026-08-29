# studylife-cli

A command-line client for [StudyLife](https://github.com/lukislp/studylife), the self-hosted
study organizer. Manage notes, sessions, course goals, and webhooks from your terminal - scripts
and shells welcome.

## Install

```bash
pip install git+https://github.com/lukislp/studylife-cli
```

(PyPI publishing is planned; until then, install straight from GitHub.)

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

studylife timer
studylife courses list
studylife programs list
studylife programs get 1

studylife webhooks list
studylife webhooks create https://example.com/hook session.completed
studylife webhooks delete 3
```

Add `--json` to any command for machine-readable output:

```bash
studylife notes list --json | jq '.[] | .title'
```

## Development

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## License

AGPL-3.0
