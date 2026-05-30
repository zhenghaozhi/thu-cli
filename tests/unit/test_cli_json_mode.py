"""``--json`` discipline tests.

Validate that commands with ``--json`` actually emit parseable JSON on stdout
(not table / hint / error rendered prose). Currently exercises the only command
that's safe to run offline (``whoami``); other commands need network so they're
covered by integration tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from thu_cli.cli.main import dispatch


@pytest.fixture(autouse=True)
def isolate_config_home(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("THU_CLI_HOME", str(tmp_path))
    import importlib

    from thu_cli.config import profiles as profiles_module
    importlib.reload(profiles_module)
    from thu_cli.services import auth as auth_service_module
    importlib.reload(auth_service_module)
    yield
    importlib.reload(profiles_module)
    importlib.reload(auth_service_module)


def test_whoami_json_with_no_profile_emits_json(capsys):
    rc = dispatch(["--json", "auth", "whoami"])
    assert rc == 1
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload == {"user": None}


def test_whoami_json_with_profile_emits_json(capsys):
    from thu_cli.config import profiles
    profiles.add_profile("2023012168", make_current=True)
    rc = dispatch(["--json", "auth", "whoami"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"user": "2023012168"}


def test_whoami_no_json_human_readable(capsys):
    from thu_cli.config import profiles
    profiles.add_profile("2023012168", make_current=True)
    rc = dispatch(["auth", "whoami"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out == "2023012168"


def test_thu_cli_error_emits_json_on_stderr(capsys):
    """``--json`` mode should write a JSON error object to stderr."""
    from thu_cli.cli.main import _print_thu_error
    from thu_cli.core.errors import BadCredentials

    rc = _print_thu_error(BadCredentials("wrong pwd"), json_mode=True)
    assert rc == 2
    err = capsys.readouterr().err.strip()
    payload = json.loads(err)
    assert payload["error"]["type"] == "BadCredentials"
    assert "wrong pwd" in payload["error"]["message"]


def test_thu_cli_error_human_mode_no_json(capsys):
    """Human mode should write prose, not JSON."""
    from thu_cli.cli.main import _print_thu_error
    from thu_cli.core.errors import BadCredentials

    rc = _print_thu_error(BadCredentials("wrong pwd"), json_mode=False)
    assert rc == 2
    err = capsys.readouterr().err.strip()
    try:
        json.loads(err)
        raise AssertionError("expected non-JSON human output")
    except json.JSONDecodeError:
        pass
    assert "wrong pwd" in err
