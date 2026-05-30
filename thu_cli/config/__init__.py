"""Local paths, profile registry, and CLI message catalog."""
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
