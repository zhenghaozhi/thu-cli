"""CLI smoke tests — argparser builds, --help works, no domain crashes."""
from __future__ import annotations

import pytest

from thu_cli.cli.main import _build_argparser, _discover_domain_packages


def test_argparser_builds():
    p = _build_argparser()
    assert p is not None


@pytest.mark.parametrize("domain", ["auth", "learn", "info"])
def test_domain_help_does_not_crash(domain, capsys):
    """非空 domain 的 --help 应该正常输出。"""
    p = _build_argparser()
    with pytest.raises(SystemExit) as ex:
        p.parse_args([domain, "--help"])
    assert ex.value.code == 0
    out = capsys.readouterr().out
    assert "usage:" in out


def test_empty_domains_not_registered(capsys):
    """campus / academic 当前没有命令文件 — 应**不**出现在顶层 help / 不能被调用。"""
    p = _build_argparser()
    # 顶层 help 不显示空 domain
    with pytest.raises(SystemExit):
        p.parse_args(["--help"])
    out = capsys.readouterr().out
    assert "campus" not in out
    assert "academic" not in out


def test_domain_discovery_finds_all_subpackages():
    """domain 自动发现应该枚举 cli/commands/ 下所有子包，包括空 domain。"""
    discovered = _discover_domain_packages()
    assert "auth" in discovered
    assert "learn" in discovered
    assert "info" in discovered
    assert "campus" in discovered
    assert "academic" in discovered


@pytest.mark.parametrize("path", [
    ["auth", "login", "--help"],
    ["auth", "status", "--help"],
    ["auth", "logout", "--help"],
    ["auth", "verify", "--help"],
    ["auth", "whoami", "--help"],
    ["auth", "profile", "--help"],
    ["auth", "use", "--help"],
    ["learn", "me", "--help"],
    ["learn", "course", "--help"],
    ["learn", "announcement", "--help"],
    ["learn", "file", "--help"],
    ["learn", "homework", "--help"],
    ["learn", "discussion", "--help"],
    ["learn", "question", "--help"],
    ["learn", "questionnaire", "--help"],
    ["info", "calendar", "--help"],
    ["info", "transcript", "--help"],
    ["info", "timetable", "--help"],
])
def test_each_command_help_works(path, capsys):
    p = _build_argparser()
    with pytest.raises(SystemExit) as ex:
        p.parse_args(path)
    assert ex.value.code == 0


def test_no_args_returns_zero_in_non_tty(capsys):
    from thu_cli.cli.main import main
    rc = main([], interactive=False)
    assert rc == 0
