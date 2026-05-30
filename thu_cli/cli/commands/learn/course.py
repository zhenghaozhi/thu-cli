"""``thu learn course`` command."""
from __future__ import annotations

import argparse

from ....config import M
from ..._common import CommandContext, add_network_flags
from ...output import register_renderer

NAME = "course"
HELP = "CMD_LEARN_COURSE"


def register(subparsers: argparse._SubParsersAction) -> None:
    help_text = getattr(M, HELP)
    p = subparsers.add_parser(NAME, help=help_text, description=help_text)
    add_network_flags(p)
    p.add_argument("--user", help=M.HELP_USER)
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--all", dest="all_terms", action="store_true", help=M.HELP_ALL_TERMS)
    scope.add_argument("--semester", help=M.HELP_SEMESTER)
    p.add_argument("--with-time-location", action="store_true", help=M.HELP_WITH_TIME_LOCATION)
    p.set_defaults(_handler=handle)


def _render(listing, ui) -> None:
    label = M.ALL_SEMESTERS if listing.semester == "all" else listing.semester
    ui.section(M.COURSES)
    ui.kv([
        (M.PROFILE_KEY, listing.user),
        (M.SEMESTER, label),
        (M.COUNT, str(len(listing.courses))),
    ])
    ui.line()
    if not listing.courses:
        ui.info(M.INFO_NO_COURSES)
        return
    show_time = any(c.time_locations for c in listing.courses)
    rows = []
    for c in listing.courses:
        row = [c.semester_id, c.name, c.teacher, c.id]
        if show_time:
            row.append("; ".join(c.time_locations) or c.schedule)
        rows.append(row)
    headers = [M.SEMESTER, M.COURSE, M.TEACHER, M.ID]
    if show_time:
        headers.append(M.TIME_LOCATION)
    ui.table(headers, rows)
    for w in listing.warnings:
        ui.warning(w.message)


register_renderer("learn_course", _render)


def handle(args: argparse.Namespace, ctx: CommandContext) -> int:
    user = ctx.resolve_user(args.user)
    listing = ctx.services.learn.list_courses(
        user,
        semester=args.semester,
        all_terms=args.all_terms,
        include_time_locations=args.with_time_location,
        **ctx.auth_kwargs(user),
    )
    ctx.output.render(listing, kind="learn_course")
    return 0
