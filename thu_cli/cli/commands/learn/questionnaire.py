"""``thu learn questionnaire`` command."""
from __future__ import annotations

import argparse

from ....config import M
from ....core.errors import LearnError
from ..._common import CommandContext, add_network_flags
from ...output import register_renderer

NAME = "questionnaire"
HELP = "CMD_LEARN_QUESTIONNAIRE"


def register(subparsers: argparse._SubParsersAction) -> None:
    help_text = getattr(M, HELP)
    p = subparsers.add_parser(NAME, help=help_text, description=help_text)
    add_network_flags(p)
    p.add_argument("--user", help=M.HELP_USER)
    p.add_argument("--course", help=M.HELP_COURSE_ID)
    p.add_argument("--with-detail", action="store_true", help=M.HELP_WITH_QUESTIONNAIRE_DETAIL)
    p.add_argument("--strict", action="store_true", help=M.HELP_STRICT)
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--all", dest="all_terms", action="store_true", help=M.HELP_ALL_TERMS)
    scope.add_argument("--semester", help=M.HELP_SEMESTER)
    p.set_defaults(_handler=handle)


def _render(listing, ui) -> None:
    label = M.ALL_SEMESTERS if listing.semester == "all" else listing.semester
    ui.section(M.QUESTIONNAIRES)
    ui.kv([
        (M.PROFILE_KEY, listing.user),
        (M.SEMESTER, label),
        (M.COUNT, str(len(listing.items))),
    ])
    ui.line()
    if not listing.items:
        ui.info(M.INFO_NO_QUESTIONNAIRES)
        return
    ui.table(
        [M.COURSE, M.TITLE, M.TYPE, M.DEADLINE, M.COUNT, M.ID],
        [
            [item.course_name or item.course_id, item.title, item.kind,
             item.end_at, str(len(item.questions)), item.id]
            for item in listing.items
        ],
    )
    for w in listing.warnings:
        ui.warning(w.message)


register_renderer("learn_questionnaire", _render)


def handle(args: argparse.Namespace, ctx: CommandContext) -> int:
    user = ctx.resolve_user(args.user)
    try:
        listing = ctx.services.learn.list_questionnaires(
            user, semester=args.semester, all_terms=args.all_terms,
            course_id=args.course, include_detail=args.with_detail,
            allow_failure=not args.strict, **ctx.auth_kwargs(user),
        )
    except LearnError as e:
        ctx.output.error(M.ERR_LEARN_FAILED.format(type=type(e).__name__, message=e))
        return 1
    ctx.output.render(listing, kind="learn_questionnaire")
    return 0
