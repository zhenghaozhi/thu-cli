"""Unit tests for ``config.i18n`` language selection."""
from __future__ import annotations


def test_default_is_zh(monkeypatch):
    monkeypatch.delenv("THU_CLI_LANG", raising=False)
    monkeypatch.delenv("LANG", raising=False)
    from thu_cli.config.i18n import ZH, M
    assert M.PROFILE == "Profile"
    assert M.AUTH_DESC == ZH["AUTH_DESC"]


def test_explicit_en(monkeypatch):
    monkeypatch.setenv("THU_CLI_LANG", "en_US.UTF-8")
    from thu_cli.config.i18n import M
    assert M.AUTH_DESC == "Tsinghua Single Sign-On"


def test_lang_fallback(monkeypatch):
    monkeypatch.delenv("THU_CLI_LANG", raising=False)
    monkeypatch.setenv("LANG", "en_GB.UTF-8")
    from thu_cli.config.i18n import M
    assert M.AUTH_DESC.startswith("Tsinghua")


def test_unknown_key_raises(monkeypatch):
    monkeypatch.delenv("THU_CLI_LANG", raising=False)
    from thu_cli.config.i18n import M
    try:
        _ = M.THIS_KEY_DEFINITELY_DOES_NOT_EXIST
    except AttributeError:
        pass
    else:
        raise AssertionError("expected AttributeError")
