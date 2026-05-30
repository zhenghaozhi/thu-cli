"""Unit tests for ``core.webvpn``."""
from __future__ import annotations

import pytest

from thu_cli.core.webvpn import WEBVPN_HOST_HASH, webvpn_translate, webvpn_url


def test_webvpn_url_builds_correctly():
    url = webvpn_url("zhjw.cic.tsinghua.edu.cn", "/foo/bar?x=1")
    expected = (
        "https://webvpn.tsinghua.edu.cn/https/"
        "77726476706e69737468656265737421eaff4b8b69336153301c9aa596522b20bc86e6e559a9b290"
        "/foo/bar?x=1"
    )
    assert url == expected


def test_webvpn_url_prepends_slash():
    a = webvpn_url("info.tsinghua.edu.cn", "/path")
    b = webvpn_url("info.tsinghua.edu.cn", "path")
    assert a == b


def test_webvpn_url_unknown_host_raises():
    with pytest.raises(KeyError):
        webvpn_url("does-not-exist.tsinghua.edu.cn", "/x")


def test_webvpn_translate_https_host():
    raw = "https://info.tsinghua.edu.cn/f/info/gxfw_fg/common/index"
    out = webvpn_translate(raw)
    h = WEBVPN_HOST_HASH["info.tsinghua.edu.cn"]
    assert out == f"https://webvpn.tsinghua.edu.cn/https/{h}/f/info/gxfw_fg/common/index"


def test_webvpn_translate_with_port():
    raw = "https://zhjw.cic.tsinghua.edu.cn:8080/some/path"
    out = webvpn_translate(raw)
    h = WEBVPN_HOST_HASH["zhjw.cic.tsinghua.edu.cn"]
    assert out == f"https://webvpn.tsinghua.edu.cn/https-8080/{h}/some/path"


def test_webvpn_translate_ip_form_rejected_without_hash():
    with pytest.raises(KeyError):
        webvpn_translate("http://1.2.3.4:80/path")


def test_webvpn_translate_unknown_host_raises():
    with pytest.raises(KeyError):
        webvpn_translate("https://does-not-exist.tsinghua.edu.cn/x")
