"""终端 prompts + AuthInteraction 构造。

把 argparse Namespace 翻译成 ``AuthInteraction`` / ``AuthNetwork`` / ``AuthPolicy``。
这是**唯一**允许构造 AuthInteraction 的地方（架构测试钉死）— 避免每个命令文件重复
组装 14-kwarg fanout。
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


# ============================================================================
# user / password 输入
# ============================================================================
def read_user(arg_user: str | None = None, *, use_current: bool = True) -> str:
    """凭据来源：``arg_user`` > ``$THU_USER`` > current profile > 交互。

    非 tty 且都缺失抛 ``AuthError``。
    """
    try:
        user = profiles.resolve_user(arg_user, use_current=use_current)
    except ValueError as e:
        raise AuthError(str(e)) from e
    if user:
        return user
    if not sys.stdin.isatty():
        raise AuthError(
            "缺学号：请设置 THU_USER、用 --user 指定、先 `thu auth use <id>`，或在交互式终端运行"
        )
    return ui.prompt(M.PROMPT_USER)


def read_passwd() -> str:
    """``$THU_PASS`` 优先；否则 tty 用 getpass；非 tty 且无 env 抛 ``AuthError``。"""
    p = os.environ.get("THU_PASS", "")
    if p:
        return p
    if not sys.stdin.isatty():
        raise AuthError("缺密码：请设置 THU_PASS 或在交互式终端运行")
    try:
        return ui.secret(M.PROMPT_PASSWORD)
    except EOFError as e:
        raise AuthError("缺密码：请设置 THU_PASS 或在交互式终端运行") from e


# ============================================================================
# 2FA / captcha 回调
# ============================================================================
def choose_2fa(approaches_obj: dict) -> str:
    """从 ``FIND_APPROACHES`` 返回的选项里让用户选一个。"""
    options: list[tuple[str, str]] = []
    if approaches_obj.get("hasWeChatBool"):
        options.append(("wechat", "企业微信"))
    if approaches_obj.get("phone"):
        options.append(("mobile", f"手机短信 {approaches_obj['phone']}"))
    if approaches_obj.get("hasTotp"):
        options.append(("totp", "TOTP 动态口令"))
    if not options:
        raise AuthError(f"账号未绑定任何 2FA 方式：{approaches_obj}")
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


def trust_device_choice(opt: str) -> bool | str | Callable[[], bool]:
    """归一化 ``--trust-device`` 字符串到 ``AuthInteraction.trust_device`` 接受的类型。"""
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


# ============================================================================
# 构造 AuthInteraction / AuthNetwork / AuthPolicy
# ============================================================================
def build_interaction(args: argparse.Namespace, captcha_path: Path) -> AuthInteraction:
    """把 argparse + 终端回调装成 AuthInteraction。

    ``--trust-device`` 只在 ``thu auth login`` 上存在；对其它命令安静地默认 no-trust。
    """
    trust_arg = getattr(args, "trust_device", None)
    trust = trust_device_choice(trust_arg) if trust_arg is not None else False
    return AuthInteraction(
        passwd_fn=read_passwd,
        on_2fa_choice=choose_2fa,
        on_code=read_code,
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
    "read_code",
    "read_passwd",
    "read_user",
    "trust_device_choice",
]
