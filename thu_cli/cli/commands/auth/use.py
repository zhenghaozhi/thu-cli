"""``thu auth use`` — 切换 / 创建当前 profile。"""
from __future__ import annotations

import argparse

from ....config import M
from ..._common import CommandContext

NAME = "use"
HELP = "切换当前 profile；不存在则创建"


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(NAME, help=HELP, description=HELP)
    p.add_argument("user")
    p.set_defaults(_handler=handle)


def handle(args: argparse.Namespace, ctx: CommandContext) -> int:
    try:
        user = ctx.services.auth.use_profile(args.user)
    except ValueError as e:
        ctx.output.error(M.ERR_INVALID_PROFILE.format(detail=e))
        return 1
    ctx.output.success(M.OK_PROFILE_CURRENT.format(user=user))
    return 0
