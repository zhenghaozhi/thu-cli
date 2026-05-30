"""``config`` — 本地路径 / profile / i18n。

仅被 ``cli`` 和 ``services`` 引用；``sdk`` 不依赖本层（架构 test 钉死）。

公开点：

    profile_paths(user)          ProfilePaths（session / device / stage / captcha）
    add_profile / remove_profile / set_current_user / get_current_user / list_profiles
    resolve_user                 解析参数 / 环境变量 / 当前 profile
    normalize_user / STUDENT_TYPES
    get_student_type / set_student_type
    M                            消息文案代理（按 $THU_CLI_LANG / $LANG 切 zh/en）
"""
from __future__ import annotations

from .i18n import M
from .profiles import (
    STUDENT_TYPES,
    ProfilePaths,
    add_profile,
    get_current_user,
    get_student_type,
    list_profiles,
    normalize_user,
    profile_paths,
    remove_profile,
    resolve_user,
    set_current_user,
    set_student_type,
)

__all__ = [
    "M",
    "ProfilePaths",
    "STUDENT_TYPES",
    "add_profile",
    "get_current_user",
    "get_student_type",
    "list_profiles",
    "normalize_user",
    "profile_paths",
    "remove_profile",
    "resolve_user",
    "set_current_user",
    "set_student_type",
]
