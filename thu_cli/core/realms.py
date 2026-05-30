"""Realm definitions for independently bootstrapped cookie scopes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .webvpn import WEBVPN_BASE


@dataclass(frozen=True)
class Realm:
    """One externally reachable site identity."""
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
    # No clean verify endpoint; the webvpn root is the least invasive probe.
    verify_url=f"{WEBVPN_BASE}/",
    bootstrap_kind="oauth",
)


REALMS: dict[str, Realm] = {r.id: r for r in (LEARN_REALM, WEBVPN_REALM)}


__all__ = ["LEARN_REALM", "REALMS", "Realm", "WEBVPN_REALM"]
