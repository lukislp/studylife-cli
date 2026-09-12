"""Atheris fuzz harness for the API models and the login callback parser.

Contract under test: the StudyLife DTO models either validate a JSON body or raise pydantic's
ValidationError - never anything else; the loopback callback parser and the constant-time
state comparison never raise for any query string.

Run locally (Linux, needs the atheris wheel):
    uv sync --frozen --group fuzz
    uv run python fuzz/fuzz_models_and_callback.py -max_total_time=60
CI runs the same harness for a short, fixed time budget (see .github/workflows/ci.yml).
"""

from __future__ import annotations

import contextlib
import sys

import atheris
from pydantic import ValidationError

from studylife_cli.credentials import Credentials
from studylife_cli.login import _parse_callback_query, _states_match
from studylife_cli.models import (
    Course,
    CourseGoal,
    MetricsSummary,
    Note,
    Session,
    StudyProgramDetail,
    StudyProgramSummary,
    TimerState,
    Webhook,
    Whoami,
)

MODELS = (
    Course,
    CourseGoal,
    MetricsSummary,
    Note,
    Session,
    StudyProgramDetail,
    StudyProgramSummary,
    TimerState,
    Webhook,
    Whoami,
    Credentials,
)


def test_one_input(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    query = fdp.ConsumeUnicodeNoSurrogates(256)
    result = _parse_callback_query(query)
    _states_match(result.state, fdp.ConsumeUnicodeNoSurrogates(64))
    body = fdp.ConsumeBytes(512)
    for model in MODELS:
        with contextlib.suppress(ValidationError):
            model.model_validate_json(body)


if __name__ == "__main__":
    # instrument_all() instead of instrument_imports(): the package is loaded through uv's
    # editable-install loader, which the import hook does not see (no coverage feedback,
    # so libFuzzer would never grow its inputs past a few bytes).
    atheris.instrument_all()
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
