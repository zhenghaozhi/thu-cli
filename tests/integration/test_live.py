"""Integration test: live verify against id.tsinghua + webvpn.

Gated on ``THU_RUN_INTEGRATION=1`` + ``THU_USER`` + ``THU_PASS``. Default skip.

Run manually:

    THU_RUN_INTEGRATION=1 THU_USER=2023012168 THU_PASS=... \\
      .venv/bin/pytest tests/integration -x -v

Each test goes through the real ``LearnService`` / ``InfoService``. **2FA** may
prompt interactively. Tests are kept tiny to minimise 2FA frequency.
"""
from __future__ import annotations

import os

import pytest

_RUN = os.environ.get("THU_RUN_INTEGRATION") == "1"
_USER = os.environ.get("THU_USER")
_HAS_PASS = bool(os.environ.get("THU_PASS"))

requires_live = pytest.mark.skipif(
    not (_RUN and _USER and _HAS_PASS),
    reason="integration test gated by THU_RUN_INTEGRATION=1 + THU_USER + THU_PASS",
)


@requires_live
def test_learn_me():
    from thu_cli.services.learn import LearnService
    svc = LearnService()
    result = svc.user_info(_USER)
    print(f"\n  user: {result.user}")
    print(f"  name: {result.info.name}")
    print(f"  dept: {result.info.department}")
    assert result.user == _USER
    assert result.info.name


@requires_live
def test_info_calendar():
    from thu_cli.services.info import InfoService
    svc = InfoService()
    cal = svc.get_calendar(_USER)
    print(f"\n  semester: {cal.semester_id}")
    print(f"  first day: {cal.first_day}")
    print(f"  weeks: {cal.week_count}")
    assert cal.semester_id
    assert cal.first_day
    assert cal.week_count in (12, 18)
