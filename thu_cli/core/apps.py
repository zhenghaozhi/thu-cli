"""CampusApp — webvpn realm 内的具体 app。

bootstrap policy 两种：

    id      — 重新 POST 凭证到 ``id.tsinghua/.../login/check``，APP_ID 决定 ticket
              issue 给哪个 app。``INFO_PORTAL`` 是典型例子。
    default — 必须 ``INFO_PORTAL`` 已 bootstrap。GET info portal 的
              ``onlineAppRedirect?yyfwid=<this_app>&_csrf=<info_csrf>`` 拿一个
              roaming URL，跟过去激活该 app 在 webvpn 代理里的 cookies。
              ``TRANSCRIPT`` / ``TIMETABLE`` 等都是这种。

未来要加新 CampusApp（图书馆 / 电费 / ...）按相同模板新增 dataclass 即可，
``SsoSession.ensure_app(app)`` 会按 policy 自动选 bootstrap 路径。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .realms import WEBVPN_REALM, Realm


@dataclass(frozen=True)
class CampusApp:
    """webvpn realm 内的一个 app。

    字段：
        id          短名
        policy      "id" = 重发凭证 / "default" = 走 info portal 的 onlineAppRedirect
        realm       目前都是 WEBVPN_REALM
        sso_app_id  id.tsinghua 的 APP_ID（policy=id 用）
        yyfwid      info portal 应用 id（policy=default 用）
        parent_app  policy=default 必须先 bootstrap 的父 app；通常是 INFO_PORTAL
        verify_url  存活检查 URL；为空则按 bootstrap 时间戳判定
    """
    id: str
    policy: Literal["id", "default"]
    realm: Realm
    sso_app_id: str = ""
    yyfwid: str = ""
    parent_app: CampusApp | None = None
    verify_url: str = ""


# ---------------- 现役 app 实例 ----------------
INFO_PORTAL = CampusApp(
    id="info_portal",
    policy="id",
    realm=WEBVPN_REALM,
    sso_app_id="10000ea055dd8d81d09d5a1ba55d39ad",
    # INFO_USER_DATA_URL 需要 ?_csrf=<token>，而拿 token 又要 INFO_PORTAL 活着 — 鸡蛋互斥。
    # 留空 verify_url 让 verify_app 走 "信任 bootstrap 时间戳" 路径；若实际过期，下一个
    # default-policy app bootstrap 时 onlineAppRedirect 会返回 "用户未登录"，service
    # 层 with_reauth 接住并重 bootstrap。
    verify_url="",
)


# 教务（zhjw）transcript / timetable，按本科/研究生区分。
TRANSCRIPT_BKS = CampusApp(
    id="transcript_bks",
    policy="default",
    realm=WEBVPN_REALM,
    yyfwid="B7EF0ADF9406335AD7905B30CD7B49B1",
    parent_app=INFO_PORTAL,
    # transcript 的 GET 不需要 query — verify_url 直接 ping。
    verify_url="",
)

TRANSCRIPT_YJS = CampusApp(
    id="transcript_yjs",
    policy="default",
    realm=WEBVPN_REALM,
    yyfwid="E35232808C08C8C5F199F13BF6B7F5D0",
    parent_app=INFO_PORTAL,
    verify_url="",
)

TIMETABLE_BKS = CampusApp(
    id="timetable_bks",
    policy="default",
    realm=WEBVPN_REALM,
    yyfwid="287C0C6D90ABB364CD5FDF1495199962",
    parent_app=INFO_PORTAL,
    verify_url="",
)

TIMETABLE_YJS = CampusApp(
    id="timetable_yjs",
    policy="default",
    realm=WEBVPN_REALM,
    yyfwid="BEABB32641DC4EC3510B048BAF42471A",
    parent_app=INFO_PORTAL,
    verify_url="",
)


CAMPUS_APPS: dict[str, CampusApp] = {
    a.id: a for a in (
        INFO_PORTAL,
        TRANSCRIPT_BKS, TRANSCRIPT_YJS,
        TIMETABLE_BKS, TIMETABLE_YJS,
    )
}


__all__ = [
    "CAMPUS_APPS",
    "CampusApp",
    "INFO_PORTAL",
    "TIMETABLE_BKS",
    "TIMETABLE_YJS",
    "TRANSCRIPT_BKS",
    "TRANSCRIPT_YJS",
]
