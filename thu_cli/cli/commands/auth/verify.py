"""``thu auth verify`` command."""
from __future__ import annotations

import argparse

from ....config import M
from ..._common import CommandContext, add_network_flags
from ...prompts import build_network

NAME = "verify"
HELP = "CMD_AUTH_VERIFY"


def register(subparsers: argparse._SubParsersAction) -> None:
    help_text = getattr(M, HELP)
    p = subparsers.add_parser(NAME, help=help_text, description=help_text)
    add_network_flags(p)
    p.add_argument("--user", help=M.HELP_USER)
    p.set_defaults(_handler=handle)


def handle(args: argparse.Namespace, ctx: CommandContext) -> int:
    user = ctx.services.auth.resolve_user(args.user)
    ok = ctx.services.auth.verify(user, network=build_network(args, on_event=ctx.output.emit))
    if ok:
        ctx.output.success(M.OK_SESSION_VALID.format(user=user))
        return 0
    ctx.output.warning(M.WARN_SESSION_EXPIRED.format(user=user))
    return 2
