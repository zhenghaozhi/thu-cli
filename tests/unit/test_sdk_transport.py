"""Unit tests for ``sdk.transport``."""
from __future__ import annotations

from pathlib import Path

import pytest

from thu_cli.core.errors import SessionExpired
from thu_cli.sdk.transport import (
    RemoteFile,
    content_disposition_filename,
    display_size,
    display_time,
    safe_filename,
    unique_path,
)


@pytest.mark.parametrize("raw,expected", [
    ("normal.pdf", "normal.pdf"),
    ("with/slash.pdf", "with_slash.pdf"),
    ("with:colon.pdf", "with_colon.pdf"),
    ("  .hidden  ", "hidden"),
    ("", "download"),
])
def test_safe_filename(raw, expected):
    assert safe_filename(raw) == expected


def test_unique_path_no_conflict(tmp_path: Path):
    target = tmp_path / "file.txt"
    assert unique_path(target) == target


def test_unique_path_appends_suffix(tmp_path: Path):
    target = tmp_path / "file.txt"
    target.touch()
    assert unique_path(target) == tmp_path / "file-1.txt"


def test_unique_path_skips_existing(tmp_path: Path):
    (tmp_path / "file.txt").touch()
    (tmp_path / "file-1.txt").touch()
    assert unique_path(tmp_path / "file.txt") == tmp_path / "file-2.txt"


def test_content_disposition_basic():
    assert content_disposition_filename('attachment; filename="hello.pdf"') == "hello.pdf"


def test_content_disposition_utf8_star():
    out = content_disposition_filename("attachment; filename*=UTF-8''hello%20world.pdf")
    assert out == "hello world.pdf"


def test_content_disposition_none():
    assert content_disposition_filename(None) is None
    assert content_disposition_filename("") is None


def test_display_time_ms_timestamp():
    # 2025-01-01 00:00:00 UTC is 1735689600000ms — but display_time uses local tz, so
    # just assert the format
    out = display_time("1735689600000")
    assert "2024" in out or "2025" in out
    assert ":" in out


def test_display_time_passthrough():
    assert display_time("not a timestamp") == "not a timestamp"
    assert display_time(None) == ""
    assert display_time("") == ""


def test_display_size():
    assert display_size("1024") == "1.0 KB"
    assert display_size("0") == "0 B"
    assert display_size("not digits") == "not digits"
    assert display_size(None) == ""


def test_remote_file_filename():
    rf = RemoteFile(id="x", name="my file.pdf", download_url="https://e/d")
    assert rf.filename() == "my file.pdf"


def test_remote_file_filename_sanitizes():
    rf = RemoteFile(id="x", name="bad/name.pdf", download_url="https://e/d")
    assert rf.filename() == "bad_name.pdf"

def test_csrf_params_missing_token_raises():
    import requests

    from thu_cli.sdk.transport import csrf_params
    s = requests.Session()
    with pytest.raises(SessionExpired):
        csrf_params(s, domain="learn.tsinghua.edu.cn")


def test_json_or_expired_redirect_raises():
    import requests

    from thu_cli.sdk.transport import json_or_expired
    r = requests.Response()
    r.status_code = 302
    r.headers["Content-Type"] = "text/html"
    with pytest.raises(SessionExpired):
        json_or_expired(r)
