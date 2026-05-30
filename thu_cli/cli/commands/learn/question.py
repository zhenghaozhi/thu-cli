"""``thu learn question`` command."""
from __future__ import annotations

import argparse

from ....config import M
from ....core.errors import LearnError
from ..._common import CommandContext, add_network_flags
from ...output import register_renderer

NAME = "question"
HELP = "CMD_LEARN_QUESTION"


def register(subparsers: argparse._SubParsersAction) -> None:
    help_text = getattr(M, HELP)
    p = subparsers.add_parser(NAME, help=help_text, description=help_text)
    add_network_flags(p)
    p.add_argument("--user", help=M.HELP_USER)
    p.add_argument("--course", help=M.HELP_COURSE_ID)
    p.add_argument("--strict", action="store_true", help=M.HELP_STRICT)
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--all", dest="all_terms", action="store_true", help=M.HELP_ALL_TERMS)
    scope.add_argument("--semester", help=M.HELP_SEMESTER)
    p.set_defaults(_handler=handle)


def _render(listing, ui) -> None:
    label = M.ALL_SEMESTERS if listing.semester == "all" else listing.semester
    ui.section(M.QUESTIONS)
    ui.kv([
        (M.PROFILE_KEY, listing.user),
        (M.SEMESTER, label),
        (M.COUNT, str(len(listing.items))),
    ])
    ui.line()
    if not listing.items:
        ui.info(M.INFO_NO_QUESTIONS)
        return
    ui.table(
        [M.PUBLISHED_AT, M.COURSE, M.TITLE, M.COUNT, M.ID],
        [
            [item.published_at, item.course_name or item.course_id,
             item.title, str(item.reply_count), item.id]
            for item in listing.items
        ],
    )
    for w in listing.warnings:
        ui.warning(w.message)


register_renderer("learn_question", _render)


def handle(args: argparse.Namespace, ctx: CommandContext) -> int:
    user = ctx.resolve_user(args.user)
    try:
        listing = ctx.services.learn.list_questions(
            user, semester=args.semester, all_terms=args.all_terms,
            course_id=args.course, allow_failure=not args.strict,
            **ctx.auth_kwargs(user),
        )
    except LearnError as e:
        ctx.output.error(M.ERR_LEARN_FAILED.format(type=type(e).__name__, message=e))
        return 1
    ctx.output.render(listing, kind="learn_question")
    return 0
