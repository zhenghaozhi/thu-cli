"""``thu learn me`` command."""
from __future__ import annotations

import argparse

from ....config import M
from ..._common import CommandContext, add_network_flags
from ...output import register_renderer

NAME = "me"
HELP = "CMD_LEARN_ME"


def register(subparsers: argparse._SubParsersAction) -> None:
    help_text = getattr(M, HELP)
    p = subparsers.add_parser(NAME, help=help_text, description=help_text)
    add_network_flags(p)
    p.add_argument("--user", help=M.HELP_USER)
    p.set_defaults(_handler=handle)


def _render(result, ui) -> None:
    ui.section(M.PROFILE)
    ui.kv([
        (M.PROFILE_KEY, result.user),
        (M.NAME, result.info.name or M.UNKNOWN),
        (M.DEPARTMENT, result.info.department or M.UNKNOWN),
    ])


register_renderer("learn_me", _render)


def handle(args: argparse.Namespace, ctx: CommandContext) -> int:
    user = ctx.resolve_user(args.user)
    result = ctx.services.learn.user_info(user, **ctx.auth_kwargs(user))
    ctx.output.render(result, kind="learn_me")
    return 0
