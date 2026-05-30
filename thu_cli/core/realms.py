"""Realm — 一个对外可访问的站点身份。

每个 realm 是 ``SsoSession`` 可以独立 bootstrap 的一份 cookie 空间。一份凭证只需
bootstrap 每个 realm 一次，之后跨 realm 共享设备指纹。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .webvpn import WEBVPN_BASE


@dataclass(frozen=True)
class Realm:
    """一个公网可达的站点。

    字段：
        id              短名（"learn" / "webvpn" / ...）
        sso_app_id      id.tsinghua 上对应的 APP_ID
        entry_url       第一步 GET 的 URL；之后跟 redirect 链到 id.tsinghua 的登录表单
        cookie_domain   该 realm 被视为 "已 bootstrap" 的 cookie 域
        verify_url      ping 这个 URL 来判活
        bootstrap_kind  "direct"：entry_url 就是 id.tsinghua 表单页
                        "oauth"：entry_url 是 realm 站点，OAuth 跳转到 id
    """
    id: str
    sso_app_id: str
    entry_url: str
    cookie_domain: str
    verify_url: str
    bootstrap_kind: Literal["direct", "oauth"]


LEARN_REALM = Realm(
    id="learn",
    sso_app_id="bb5df85216504820be7bba2b0ae1535b",
    entry_url="https://id.tsinghua.edu.cn/do/off/ui/auth/login/form/bb5df85216504820be7bba2b0ae1535b/0",
    cookie_domain="learn.tsinghua.edu.cn",
    verify_url="https://learn.tsinghua.edu.cn/b/kc/zhjw_v_code_xnxq/getCurrentAndNextSemester",
    bootstrap_kind="direct",
)

WEBVPN_REALM = Realm(
    id="webvpn",
    sso_app_id="20843963f89b3072788f7fe75a5d9322",
    entry_url=f"{WEBVPN_BASE}/login?oauth_login=true",
    cookie_domain="webvpn.tsinghua.edu.cn",
    # 没有干净的 verify endpoint；info portal 的根路径作为存活检查。
    verify_url=f"{WEBVPN_BASE}/",
    bootstrap_kind="oauth",
)


REALMS: dict[str, Realm] = {r.id: r for r in (LEARN_REALM, WEBVPN_REALM)}


__all__ = ["LEARN_REALM", "REALMS", "Realm", "WEBVPN_REALM"]
