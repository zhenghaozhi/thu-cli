"""``thu info timetable`` command."""
from __future__ import annotations

import argparse
from datetime import datetime

from ....config import M
from ..._common import CommandContext, add_network_flags
from ...output import register_renderer

NAME = "timetable"
HELP = "CMD_INFO_TIMETABLE"


def register(subparsers: argparse._SubParsersAction) -> None:
    help_text = getattr(M, HELP)
    p = subparsers.add_parser(NAME, help=help_text, description=help_text)
    add_network_flags(p)
    p.add_argument("--user", help=M.HELP_USER)
    p.add_argument("--start", help=M.HELP_TIMETABLE_START)
    p.add_argument("--end", help=M.HELP_TIMETABLE_END)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--graduate", action="store_true", help=M.HELP_GRADUATE)
    g.add_argument("--undergraduate", action="store_true", help=M.HELP_UNDERGRADUATE)
    p.set_defaults(_handler=handle)


def _render(events, ui) -> None:
    ui.section(M.TIMETABLE)
    if not events:
        ui.info(M.INFO_NO_TIMETABLE)
        return
    rows = [
        [e.date, f"{e.begin}-{e.end}", e.kind, e.title, e.location]
        for e in events
    ]
    ui.table([M.DATE, M.TIME_SLOT, M.TYPE, M.NAME, M.LOCATION], rows)


register_renderer("info_timetable", _render)


def _validate_date(field: str, value: str | None) -> None:
    if not value:
        return
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(M.ERR_DATE_FORMAT.format(field=field, value=value)) from e


def handle(args: argparse.Namespace, ctx: CommandContext) -> int:
    _validate_date("--start", args.start)
    _validate_date("--end", args.end)
    user = ctx.resolve_user(args.user)
    graduate: bool | None = None
    if args.graduate:
        graduate = True
    elif args.undergraduate:
        graduate = False
    events = ctx.services.info.get_timetable(
        user,
        start_date=args.start,
        end_date=args.end,
        graduate=graduate,
        **ctx.auth_kwargs(user),
    )
    ctx.output.render(events, kind="info_timetable")
    return 0
