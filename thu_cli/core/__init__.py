"""Core data types, pure helpers, and endpoint constants."""
from __future__ import annotations

from .apps import (
    CAMPUS_APPS,
    INFO_PORTAL,
    TIMETABLE_BKS,
    TIMETABLE_YJS,
    TRANSCRIPT_BKS,
    TRANSCRIPT_YJS,
    CampusApp,
)
from .errors import (
    AuthError,
    BadCredentials,
    CaptchaRequired,
    LearnError,
    LearnFailReason,
    SessionExpired,
    ThuCliError,
    TwoFactorFailed,
    TwoFactorPending,
)
from .realms import (
    LEARN_REALM,
    REALMS,
    WEBVPN_REALM,
    Realm,
)
from .webvpn import (
    WEBVPN_BASE,
    WEBVPN_HOST_HASH,
    webvpn_translate,
    webvpn_url,
)

__all__ = [
    "AuthError",
    "BadCredentials",
    "CAMPUS_APPS",
    "CampusApp",
    "CaptchaRequired",
    "INFO_PORTAL",
    "LEARN_REALM",
    "LearnError",
    "LearnFailReason",
    "REALMS",
    "Realm",
    "SessionExpired",
    "ThuCliError",
    "TIMETABLE_BKS",
    "TIMETABLE_YJS",
    "TRANSCRIPT_BKS",
    "TRANSCRIPT_YJS",
    "TwoFactorFailed",
    "TwoFactorPending",
    "WEBVPN_BASE",
    "WEBVPN_HOST_HASH",
    "WEBVPN_REALM",
    "webvpn_translate",
    "webvpn_url",
]
