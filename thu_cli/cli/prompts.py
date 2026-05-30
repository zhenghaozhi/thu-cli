"""Terminal prompts and auth option builders.

This module translates ``argparse.Namespace`` into ``AuthInteraction``,
``AuthNetwork``, and ``AuthPolicy``. It is the only place that should build
``AuthInteraction`` for CLI commands, keeping auth callback wiring centralized.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from pathlib import Path

from ..config import M, profiles
from ..core.errors import AuthError
from ..sdk.auth import AuthInteraction, AuthNetwork, AuthPolicy
from .output import ui


def read_user(arg_user: str | None = None, *, use_current: bool = True) -> str:
    """Resolve user from ``arg_user`` > ``$THU_USER`` > current profile > prompt."""
    try:
        user = profiles.resolve_user(arg_user, use_current=use_current)
    except ValueError as e:
        raise AuthError(str(e)) from e
    if user:
        return user
    if not sys.stdin.isatty():
        raise AuthError(M.ERR_MISSING_USER)
    return ui.prompt(M.PROMPT_USER)


def read_passwd() -> str:
    """Read password from ``$THU_PASS`` or an interactive secret prompt."""
    p = os.environ.get("THU_PASS", "")
    if p:
        return p
    if not sys.stdin.isatty():
        raise AuthError(M.ERR_MISSING_PASSWORD)
    try:
        return ui.secret(M.PROMPT_PASSWORD)
    except EOFError as e:
        raise AuthError(M.ERR_MISSING_PASSWORD) from e


def choose_2fa(approaches_obj: dict) -> str:
    """Ask the user to choose one option from ``FIND_APPROACHES``."""
    options: list[tuple[str, str]] = []
    if approaches_obj.get("hasWeChatBool"):
        options.append(("wechat", M.METHOD_2FA_WECHAT))
    if approaches_obj.get("phone"):
        options.append(("mobile", M.METHOD_2FA_MOBILE.format(phone=approaches_obj["phone"])))
    if approaches_obj.get("hasTotp"):
        options.append(("totp", M.METHOD_2FA_TOTP))
    if not options:
        raise AuthError(f"account has no 2FA method bound: {approaches_obj}")
    if len(options) == 1:
        return options[0][0]

    ui.section(M.TWO_FACTOR)
    ui.table([M.INDEX, M.METHOD], [[idx, desc] for idx, (_, desc) in enumerate(options, 1)])
    while True:
        choice = ui.prompt(M.PROMPT_2FA_CHOICE.format(count=len(options)))
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1][0]


def read_code(prompt: str) -> str:
    return ui.prompt(prompt.rstrip(": "))


def code_prompt(choice: str) -> str:
    return {
        "wechat": M.PROMPT_2FA_CODE_WECHAT,
        "mobile": M.PROMPT_2FA_CODE_MOBILE,
        "totp": M.PROMPT_2FA_CODE_TOTP,
    }.get(choice, choice)


def trust_device_choice(opt: str) -> bool | str | Callable[[], bool]:
    """Normalize ``--trust-device`` into an ``AuthInteraction`` value."""
    if opt == "ask":
        return lambda: ui.confirm(M.PROMPT_TRUST_DEVICE, default=False)
    return {"yes": True, "no": False}[opt]


def captcha_prompt(path: Path) -> Callable[[bytes], str]:
    def _read_captcha(image_bytes: bytes) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(image_bytes)
        ui.warning(M.WARN_CAPTCHA_SAVED.format(path=path))
        return ui.prompt(M.PROMPT_CAPTCHA)
    return _read_captcha

def build_interaction(args: argparse.Namespace, captcha_path: Path) -> AuthInteraction:
    """Build ``AuthInteraction`` from argparse and terminal callbacks."""
    trust_arg = getattr(args, "trust_device", None)
    trust = trust_device_choice(trust_arg) if trust_arg is not None else False
    return AuthInteraction(
        passwd_fn=read_passwd,
        on_2fa_choice=choose_2fa,
        on_code=read_code,
        code_prompt=code_prompt,
        on_captcha=captcha_prompt(captcha_path),
        trust_device=trust,
    )


def build_network(
    args: argparse.Namespace,
    *,
    debug_dir: Path | None = None,
    on_event: Callable[[str, str], None] | None = None,
) -> AuthNetwork:
    return AuthNetwork(
        verify_tls=not getattr(args, "insecure", False),
        trust_env=not getattr(args, "no_env_proxy", False),
        debug_dir=debug_dir,
        on_event=on_event,
    )


def build_policy(args: argparse.Namespace) -> AuthPolicy:
    return AuthPolicy(
        prefer_2fa=getattr(args, "prefer_2fa", None),
        single_login=not getattr(args, "no_single_login", False),
        force_login=getattr(args, "force", False),
    )


__all__ = [
    "build_interaction",
    "build_network",
    "build_policy",
    "captcha_prompt",
    "choose_2fa",
    "code_prompt",
    "read_code",
    "read_passwd",
    "read_user",
    "trust_device_choice",
]
