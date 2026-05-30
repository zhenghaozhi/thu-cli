"""``thu auth login`` — 登录并预热已知服务。

支持两阶段（``--stage send`` / ``--stage verify --code XXX``）以适配脚本 / 外部 2FA 代理。
"""
from __future__ import annotations

import argparse
from pathlib import Path

from ....config import M
from ..._common import CommandContext, add_network_flags

NAME = "login"
HELP = "登录并预热当前支持的服务（learn / info portal / transcript / timetable）"


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(NAME, help=HELP, description=HELP)
    add_network_flags(p)
    p.add_argument("--user", help=M.HELP_USER)
    p.add_argument("--no-single-login", action="store_true", help=M.HELP_NO_SINGLE_LOGIN)
    p.add_argument("--prefer-2fa", choices=["mobile", "wechat", "totp"], help=M.HELP_PREFER_2FA)
    p.add_argument("--trust-device", choices=["ask", "yes", "no"], default="ask",
                   help=M.HELP_TRUST_DEVICE)
    p.add_argument("--stage", choices=["send", "verify"], help=M.HELP_STAGE)
    p.add_argument("--code", help=M.HELP_CODE)
    p.add_argument("--force", action="store_true", help=M.HELP_FORCE)
    p.add_argument("--debug-dir", help=M.HELP_DEBUG_DIR)
    p.add_argument("--student-type", choices=["undergraduate", "graduate"],
                   default=None, dest="student_type", help=M.HELP_STUDENT_TYPE)
    p.set_defaults(_handler=handle)


def handle(args: argparse.Namespace, ctx: CommandContext) -> int:
    debug_dir = Path(args.debug_dir).expanduser() if args.debug_dir else None
    user = ctx.resolve_user(args.user)
    captcha = ctx.captcha_path(user)
    from ...prompts import build_interaction, build_network, build_policy
    interaction = build_interaction(args, captcha)
    network = build_network(args, debug_dir=debug_dir, on_event=ctx.output.emit)
    policy = build_policy(args)

    result = ctx.services.auth.login(
        user,
        interaction=interaction,
        network=network,
        policy=policy,
        student_type=args.student_type,
        stage=args.stage,
        code=args.code,
        force=args.force,
    )

    if result.stage_pending:
        ctx.output.success(M.OK_2FA_SENT)
        ctx.output.hint(M.HINT_STAGE_VERIFY)
        return 0
    if result.twofa_skipped:
        ctx.output.success(M.OK_LOGGED_IN_NO_2FA.format(user=result.user))
    else:
        ctx.output.success(M.OK_LOGGED_IN.format(user=result.user))
    ctx.output.hint(M.HINT_SESSION.format(path=result.session_path))
    return 0
