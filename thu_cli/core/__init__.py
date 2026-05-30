"""``core`` — 数据 + 纯函数 + URL 常量。零外部依赖。

外部可访问点：

    errors       全部异常类
    realms       Realm 定义（LEARN_REALM / WEBVPN_REALM / ...）
    apps         CampusApp 定义（INFO_PORTAL / TRANSCRIPT_BKS / ...）
    endpoints    所有 URL 常量与拼装函数（按 domain section 分块）
    webvpn       webvpn URL 改写工具 + HOST_HASH 表

下层 (sdk / services / cli) 都依赖本层；本层不允许 import 它们。
"""
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
