"""``sdk.auth`` 单元测试（不联网）。"""
from __future__ import annotations

from pathlib import Path

import pytest

from thu_cli.core.errors import AuthError
from thu_cli.sdk.auth import (
    AuthInteraction,
    AuthNetwork,
    AuthPolicy,
    Device,
    SsoSession,
    _extract_anchor_href,
    _extract_message,
    _extract_sm2_pubkey,
    _normalize_trust_device,
    dump_cookies,
    load_cookies,
    sm2_encrypt,
)


# ---------------- Device ----------------
def test_device_load_or_create_creates(tmp_path: Path):
    path = tmp_path / "device.json"
    dev = Device.load_or_create(path)
    assert path.exists()
    assert dev.fingerprint
    assert dev.singleLoginKey


def test_device_load_or_create_reloads(tmp_path: Path):
    path = tmp_path / "device.json"
    dev = Device.load_or_create(path)
    dev2 = Device.load_or_create(path)
    assert dev.fingerprint == dev2.fingerprint
    assert dev.singleLoginKey == dev2.singleLoginKey


# ---------------- SM2 ----------------
def test_sm2_encrypt_produces_04_prefix():
    pubkey = (
        "04d0c9e1ae89279fe05b435d63e3eba437bf510e09da5f71558974a19dc596724227f08dc2fc6e74bbb9d8b468d4dd5205e9b6793a3bbc48df3fdf219b3ea140e3"
    )
    cipher = sm2_encrypt("hello", pubkey)
    assert cipher.startswith("04")
    # 加密结果非确定（含随机），但应大于 64 hex chars
    assert len(cipher) > 64


# ---------------- trust_device 归一化 ----------------
def test_normalize_trust_device_bool():
    assert _normalize_trust_device(True)() is True
    assert _normalize_trust_device(False)() is False


@pytest.mark.parametrize("s", ["yes", "y", "true", "是"])
def test_normalize_trust_device_str_yes(s: str):
    assert _normalize_trust_device(s)() is True


@pytest.mark.parametrize("s", ["no", "n", "false", "否"])
def test_normalize_trust_device_str_no(s: str):
    assert _normalize_trust_device(s)() is False


def test_normalize_trust_device_callable_pass_through():
    fn = _normalize_trust_device(lambda: True)
    assert fn() is True


def test_normalize_trust_device_invalid():
    with pytest.raises(ValueError):
        _normalize_trust_device(123)  # type: ignore[arg-type]


# ---------------- HTML 解析 ----------------
def test_extract_message_msg_note():
    html = '<html><body><div id="msg_note">账号或密码不正确</div></body></html>'
    assert _extract_message(html) == "账号或密码不正确"


def test_extract_message_falls_back_to_title():
    html = "<html><head><title>Hello</title></head></html>"
    assert _extract_message(html) == "Hello"


def test_extract_message_empty():
    assert _extract_message("<html></html>") == ""


def test_extract_sm2_pubkey():
    assert _extract_sm2_pubkey('<span id="sm2publicKey">04abcdef</span>') == "04abcdef"


def test_extract_anchor_href_a_tag():
    html = '<html><body><a href="/somewhere">Go</a></body></html>'
    href = _extract_anchor_href(html, "https://example.com/here")
    assert href == "https://example.com/somewhere"


def test_extract_anchor_href_js_redirect():
    html = '<script>window.location.href = "https://example.com/x";</script>'
    href = _extract_anchor_href(html, "https://example.com/")
    assert href == "https://example.com/x"


# ---------------- SsoSession.save / load 往返 ----------------
def test_sso_save_load_roundtrip(tmp_path: Path):
    device_path = tmp_path / "device.json"
    session_path = tmp_path / "session.json"
    device = Device.load_or_create(device_path)

    sso = SsoSession(device=device)
    sso.username = "2023012168"
    sso.http.cookies.set("XSRF-TOKEN", "abc", domain="learn.tsinghua.edu.cn", path="/")
    from datetime import datetime
    sso._bootstrapped["learn"] = datetime.now()
    sso._app_bootstrapped["info_portal"] = datetime.now()
    sso.save(session_path)

    loaded = SsoSession.load(session_path, device=device)
    assert loaded is not None
    assert loaded.username == "2023012168"
    assert loaded.http.cookies.get("XSRF-TOKEN", domain="learn.tsinghua.edu.cn") == "abc"
    assert "learn" in loaded._bootstrapped
    assert "info_portal" in loaded._app_bootstrapped


def test_sso_load_nonexistent_returns_none(tmp_path: Path):
    assert SsoSession.load(tmp_path / "no.json", device=None) is None


def test_sso_save_does_not_persist_password(tmp_path: Path):
    device_path = tmp_path / "device.json"
    session_path = tmp_path / "session.json"
    device = Device.load_or_create(device_path)
    sso = SsoSession(device=device)
    sso.username = "test"
    sso._cached_password = "SECRET_PASSWORD_DO_NOT_WRITE"
    sso.save(session_path)
    content = session_path.read_text(encoding="utf-8")
    assert "SECRET_PASSWORD_DO_NOT_WRITE" not in content
    assert "password" not in content.lower()


def test_dump_response_files_chmod_600(tmp_path: Path):
    """Regression: debug dump 文件应该 0600（headers 可能含 Set-Cookie）。"""
    import requests
    debug = tmp_path / "debug"
    sso = SsoSession(debug_dir=debug)
    r = requests.Response()
    r.status_code = 200
    r._content = b"<html>x</html>"
    r.url = "https://example/x"
    r.headers["Content-Type"] = "text/html"
    r.headers["Set-Cookie"] = "SESSION=secret; Path=/"
    sso.dump_response("test", r)
    files = list(debug.iterdir())
    assert files, "no files dumped"
    for f in files:
        mode = f.stat().st_mode & 0o777
        assert mode == 0o600, f"{f.name} mode {oct(mode)} != 0600"


# ---------------- AuthInteraction 不依赖 cli ----------------
def test_auth_interaction_constructible_without_callbacks():
    """SDK 用户能不传任何 callback 就构造（虽然 ensure_realm 会因缺密码失败）。"""
    a = AuthInteraction()
    assert a.passwd_fn is None
    assert a.on_2fa_choice is None


def test_auth_network_defaults():
    n = AuthNetwork()
    # TLS 默认校验（安全姿态）
    assert n.verify_tls is True
    assert n.trust_env is True
    assert n.debug_dir is None


def test_auth_policy_defaults():
    p = AuthPolicy()
    assert p.prefer_2fa is None
    assert p.single_login is True
    assert p.force_login is False


def test_resolve_password_without_callback_raises():
    sso = SsoSession()
    with pytest.raises(AuthError):
        sso._resolve_password(AuthInteraction())


def test_resolve_password_caches_first_call():
    """``passwd_fn`` 只调一次；后续走缓存。"""
    calls = []

    def pw():
        calls.append(1)
        return "secret"

    sso = SsoSession()
    a = AuthInteraction(passwd_fn=pw)
    assert sso._resolve_password(a) == "secret"
    assert sso._resolve_password(a) == "secret"
    assert len(calls) == 1


# ---------------- dump / load cookies ----------------
def test_dump_load_cookies_roundtrip():
    import requests
    jar = requests.cookies.RequestsCookieJar()
    jar.set("a", "1", domain="x.com", path="/")
    jar.set("b", "2", domain="y.com", path="/p")
    data = dump_cookies(jar)
    new = requests.cookies.RequestsCookieJar()
    load_cookies(new, data)
    assert new.get("a", domain="x.com") == "1"
    assert new.get("b", domain="y.com") == "2"


# ---------------- 构造时的便利字段（确保接受 Path） ----------------
def test_sso_init_accepts_path_strings(tmp_path: Path):
    sso = SsoSession(
        device=None,
        debug_dir=str(tmp_path / "debug"),
        captcha_path=str(tmp_path / "cap.jpg"),
    )
    assert isinstance(sso.debug_dir, Path)
    assert isinstance(sso.captcha_path, Path)
    assert sso.debug_dir.exists()  # __init__ 应该建好 debug_dir
