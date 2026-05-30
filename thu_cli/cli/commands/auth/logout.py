"""``thu auth logout`` — 删 session（默认保留 device.json）。"""
from __future__ import annotations

import argparse

from ....config import M
from ..._common import CommandContext, add_network_flags

NAME = "logout"
HELP = "删除 session（默认保留 device.json）"


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(NAME, help=HELP, description=HELP)
    add_network_flags(p)
    p.add_argument("--user", help=M.HELP_USER)
    p.add_argument("--all", action="store_true", help=M.HELP_LOGOUT_ALL)
    p.set_defaults(_handler=handle)


def handle(args: argparse.Namespace, ctx: CommandContext) -> int:
    result = ctx.services.auth.logout(args.user, include_device=args.all)
    if result.removed:
        ctx.output.success(M.OK_REMOVED_AUTH.format(
            items=", ".join(result.removed), user=result.user,
        ))
    else:
        ctx.output.info(M.INFO_NOTHING_REMOVED.format(user=result.user))
    if result.device_kept:
        ctx.output.hint(M.HINT_DEVICE_KEPT)
    return 0
