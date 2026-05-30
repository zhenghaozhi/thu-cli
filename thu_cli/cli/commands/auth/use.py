"""``thu auth use`` command."""
from __future__ import annotations

import argparse

from ....config import M
from ..._common import CommandContext

NAME = "use"
HELP = "CMD_AUTH_USE"


def register(subparsers: argparse._SubParsersAction) -> None:
    help_text = getattr(M, HELP)
    p = subparsers.add_parser(NAME, help=help_text, description=help_text)
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
