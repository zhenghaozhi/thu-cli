"""本地 profile 注册表。

Profile 只记账号 ID + 该账号 auth 文件位置。**不存密码**。

文件布局：
    $THU_CLI_HOME/                          默认 ~/.config/thu-cli
        config.json                         {"current_user": ..., "profiles": {...}}
        users/<id>/
            session.json                    cookies + bootstrap 时间戳
            device.json                     设备指纹
            stage.json                      两阶段 2FA 的 pending 状态
            last_captcha.jpg                上一次图形验证码（debug 用）
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(os.environ.get("THU_CLI_HOME", Path.home() / ".config" / "thu-cli"))
CONFIG_PATH = CONFIG_DIR / "config.json"
USERS_DIR = CONFIG_DIR / "users"

STUDENT_TYPES = frozenset({"undergraduate", "graduate"})


@dataclass(frozen=True)
class ProfilePaths:
    user: str
    root: Path
    session: Path
    device: Path
    stage: Path
    captcha: Path


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def normalize_user(user: str) -> str:
    user = str(user or "").strip()
    if not user:
        raise ValueError("empty profile user")
    if "/" in user or "\\" in user or user in {".", ".."}:
        raise ValueError(f"invalid profile user: {user!r}")
    return user


def profile_paths(user: str) -> ProfilePaths:
    user = normalize_user(user)
    root = USERS_DIR / user
    return ProfilePaths(
        user=user,
        root=root,
        session=root / "session.json",
        device=root / "device.json",
        stage=root / "stage.json",
        captcha=root / "last_captcha.jpg",
    )


def _empty_config() -> dict[str, Any]:
    return {"current_user": None, "profiles": {}}


def _normalized_config(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        return _empty_config()
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        profiles = {}
    normalized: dict[str, dict[str, Any]] = {}
    for user, meta in profiles.items():
        try:
            normalized_user = normalize_user(str(user))
        except ValueError:
            continue
        normalized[normalized_user] = meta if isinstance(meta, dict) else {}
    current = data.get("current_user")
    try:
        current_user = normalize_user(str(current)) if current else None
    except ValueError:
        current_user = None
    if current_user and current_user not in normalized:
        normalized[current_user] = {}
    return {"current_user": current_user, "profiles": normalized}


def load_config() -> dict[str, Any]:
    return _normalized_config(_read_json(CONFIG_PATH))


def save_config(config: dict[str, Any]) -> None:
    _write_json(CONFIG_PATH, _normalized_config(config))


def list_profiles() -> list[str]:
    return sorted(load_config()["profiles"])


def get_current_user() -> str | None:
    return load_config().get("current_user")


def add_profile(user: str, *, make_current: bool = False) -> str:
    user = normalize_user(user)
    cfg = load_config()
    changed = False
    if user not in cfg["profiles"]:
        cfg["profiles"][user] = {}
        changed = True
    if make_current or not cfg.get("current_user"):
        if cfg.get("current_user") != user:
            cfg["current_user"] = user
            changed = True
    if changed:
        save_config(cfg)
    profile_paths(user).root.mkdir(parents=True, exist_ok=True)
    return user


def set_current_user(user: str) -> str:
    return add_profile(user, make_current=True)


def remove_profile(user: str, *, delete_data: bool = False) -> bool:
    """删除 profile；profile 不存在时返回 False 且不删任何文件。

    ``delete_data=True`` 仅在 profile 实际存在时才会 rmtree 其 session/device/stage 目录 —
    避免误删孤立用户目录。
    """
    user = normalize_user(user)
    cfg = load_config()
    existed = user in cfg["profiles"]
    if not existed:
        return False
    del cfg["profiles"][user]
    if cfg.get("current_user") == user:
        remaining = sorted(cfg["profiles"])
        cfg["current_user"] = remaining[0] if remaining else None
    save_config(cfg)
    if delete_data:
        shutil.rmtree(profile_paths(user).root, ignore_errors=True)
    return True


def resolve_user(arg_user: str | None = None, *, use_current: bool = True) -> str | None:
    """凭据来源优先级：``arg_user`` > ``$THU_USER`` > current profile。"""
    raw = (arg_user or os.environ.get("THU_USER", "")).strip()
    if raw:
        return normalize_user(raw)
    if use_current:
        return get_current_user()
    return None


def get_student_type(user: str) -> str:
    """返回持久化的 student type："undergraduate" 或 "graduate"。

    未设置或非法值时 fallback 到 "undergraduate"。
    """
    user = normalize_user(user)
    cfg = load_config()
    meta = cfg.get("profiles", {}).get(user, {})
    student_type = str(meta.get("student_type") or "")
    return student_type if student_type in STUDENT_TYPES else "undergraduate"


def set_student_type(user: str, student_type: str) -> None:
    user = normalize_user(user)
    if student_type not in STUDENT_TYPES:
        raise ValueError(f"invalid student_type: {student_type!r}; must be one of {sorted(STUDENT_TYPES)}")
    cfg = load_config()
    if user not in cfg["profiles"]:
        cfg["profiles"][user] = {}
    cfg["profiles"][user]["student_type"] = student_type
    save_config(cfg)


__all__ = [
    "CONFIG_DIR",
    "CONFIG_PATH",
    "ProfilePaths",
    "STUDENT_TYPES",
    "USERS_DIR",
    "add_profile",
    "get_current_user",
    "get_student_type",
    "list_profiles",
    "load_config",
    "normalize_user",
    "profile_paths",
    "remove_profile",
    "resolve_user",
    "save_config",
    "set_current_user",
    "set_student_type",
]
