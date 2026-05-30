"""``thu info calendar`` command."""
from __future__ import annotations

import argparse

from ....config import M
from ..._common import CommandContext, add_network_flags
from ...output import register_renderer

NAME = "calendar"
HELP = "CMD_INFO_CALENDAR"


def register(subparsers: argparse._SubParsersAction) -> None:
    help_text = getattr(M, HELP)
    p = subparsers.add_parser(NAME, help=help_text, description=help_text)
    add_network_flags(p)
    p.add_argument("--user", help=M.HELP_USER)
    p.set_defaults(_handler=handle)


def _render(cal, ui) -> None:
    ui.section(M.CALENDAR)
    ui.kv([
        (M.SEMESTER, cal.semester_id),
        (M.FIRST_DAY, cal.first_day),
        (M.WEEK_COUNT, str(cal.week_count)),
    ])


register_renderer("info_calendar", _render)


def handle(args: argparse.Namespace, ctx: CommandContext) -> int:
    user = ctx.resolve_user(args.user)
    cal = ctx.services.info.get_calendar(user, **ctx.auth_kwargs(user))
    ctx.output.render(cal, kind="info_calendar")
    return 0
