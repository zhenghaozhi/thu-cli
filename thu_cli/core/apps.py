"""Campus app definitions inside the webvpn realm."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .realms import WEBVPN_REALM, Realm


@dataclass(frozen=True)
class CampusApp:
    """One app reachable through the webvpn realm."""
    id: str
    policy: Literal["id", "default"]
    realm: Realm
    sso_app_id: str = ""
    yyfwid: str = ""
    parent_app: CampusApp | None = None
    verify_url: str = ""


INFO_PORTAL = CampusApp(
    id="info_portal",
    policy="id",
    realm=WEBVPN_REALM,
    sso_app_id="10000ea055dd8d81d09d5a1ba55d39ad",
    # No clean verify endpoint: INFO_USER_DATA_URL needs an XSRF token that
    # itself requires a live INFO_PORTAL session.
    verify_url="",
)


TRANSCRIPT_BKS = CampusApp(
    id="transcript_bks",
    policy="default",
    realm=WEBVPN_REALM,
    yyfwid="B7EF0ADF9406335AD7905B30CD7B49B1",
    parent_app=INFO_PORTAL,
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
