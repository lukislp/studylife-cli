"""Local credential storage for `studylife login`.

Deliberately plaintext, like every other satellite's own key store in this ecosystem
(studylife-developers' KeyStore, studylife-mcp's .env) - the key this file holds is already
narrowly scoped by ApiKeyScopes.PubliclyGrantable server-side (no settings writes, no admin
actions possible even if this file leaked), not a master credential.

Uses a global config directory rather than a per-directory .env (unlike studylife-mcp, which
always runs from one project checkout) - a CLI is invoked from anywhere, so `studylife notes list`
needs to find the same credential regardless of the current working directory.
"""

from __future__ import annotations

import contextlib
import os
import stat
from pathlib import Path

from pydantic import BaseModel


def default_credentials_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home) if config_home else Path.home() / ".config"
    return base / "studylife-cli" / "credentials.json"


class Credentials(BaseModel):
    instance_url: str
    client_id: str
    api_key: str


def load_credentials(path: Path | None = None) -> Credentials | None:
    path = path or default_credentials_path()
    if not path.exists():
        return None
    return Credentials.model_validate_json(path.read_text(encoding="utf-8"))


def save_credentials(credentials: Credentials, path: Path | None = None) -> None:
    path = path or default_credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(credentials.model_dump_json(indent=2), encoding="utf-8")
    # Best-effort on POSIX (no-op on Windows, which has no chmod bit semantics here) -
    # restrict to the owner only, same intent as ssh's own ~/.ssh/id_* permissions.
    with contextlib.suppress(OSError):
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def clear_credentials(path: Path | None = None) -> None:
    path = path or default_credentials_path()
    path.unlink(missing_ok=True)
