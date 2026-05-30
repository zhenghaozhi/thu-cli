"""``thu auth whoami`` — 打印当前 profile。"""
from __future__ import annotations

import argparse

from ....config import M
from ..._common import CommandContext
from ...output import register_renderer

NAME = "whoami"
HELP = "显示当前 profile"


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(NAME, help=HELP, description=HELP)
    p.set_defaults(_handler=handle)


def _render(payload, ui) -> None:
    user = payload.get("user")
    if user:
        ui.line(user)
    else:
        ui.error(M.ERR_NO_CURRENT_PROFILE)
        ui.hint(M.HINT_USE_PROFILE)


register_renderer("auth_whoami", _render)


def handle(args: argparse.Namespace, ctx: CommandContext) -> int:
    user = ctx.services.auth.current_user()
    ctx.output.render({"user": user}, kind="auth_whoami")
    return 0 if user else 1
