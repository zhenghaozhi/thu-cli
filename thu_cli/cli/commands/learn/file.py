"""``thu learn file`` command."""
from __future__ import annotations

import argparse

from ....config import M
from ....core.errors import LearnError
from ..._common import CommandContext, add_network_flags
from ...output import register_renderer

NAME = "file"
HELP = "CMD_LEARN_FILE"


def register(subparsers: argparse._SubParsersAction) -> None:
    help_text = getattr(M, HELP)
    p = subparsers.add_parser(NAME, help=help_text, description=help_text)
    add_network_flags(p)
    p.add_argument("file_id", nargs="?", help=M.HELP_FILE_ID)
    p.add_argument("--user", help=M.HELP_USER)
    p.add_argument("--course", help=M.HELP_COURSE_ID)
    p.add_argument("--category", help=M.HELP_FILE_CATEGORY)
    p.add_argument("--categories", action="store_true", help=M.HELP_LIST_FILE_CATEGORIES)
    p.add_argument("--dir", default="downloads", help=M.HELP_DOWNLOAD_DIR)
    p.add_argument("--strict", action="store_true", help=M.HELP_STRICT)
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--all", dest="all_terms", action="store_true", help=M.HELP_ALL_TERMS)
    scope.add_argument("--semester", help=M.HELP_SEMESTER)
    p.set_defaults(_handler=handle)


def _render_files(listing, ui) -> None:
    label = M.ALL_SEMESTERS if listing.semester == "all" else listing.semester
    ui.section(M.FILES)
    ui.kv([
        (M.PROFILE_KEY, listing.user),
        (M.SEMESTER, label),
        (M.COUNT, str(len(listing.items))),
    ])
    ui.line()
    if not listing.items:
        ui.info(M.INFO_NO_FILES)
        return
    ui.table(
        [M.UPLOADED_AT, M.COURSE, M.TITLE, M.SIZE, M.TYPE, M.ID],
        [
            [item.uploaded_at, item.course_name or item.course_id,
             item.title, item.size, item.file_type, item.file_id]
            for item in listing.items
        ],
    )
    for w in listing.warnings:
        ui.warning(w.message)


def _render_categories(listing, ui) -> None:
    label = M.ALL_SEMESTERS if listing.semester == "all" else listing.semester
    ui.section(M.FILE_CATEGORIES)
    ui.kv([
        (M.PROFILE_KEY, listing.user),
        (M.SEMESTER, label),
        (M.COUNT, str(len(listing.items))),
    ])
    ui.line()
    if not listing.items:
        ui.info(M.INFO_NO_FILE_CATEGORIES)
        return
    ui.table(
        [M.COURSE, M.TITLE, M.CREATED_AT, M.ID],
        [
            [
                next((c.name for c in listing.courses if c.id == item.course_id), item.course_id),
                item.title,
                item.created_at,
                item.id,
            ]
            for item in listing.items
        ],
    )
    for w in listing.warnings:
        ui.warning(w.message)


register_renderer("learn_files", _render_files)
register_renderer("learn_file_categories", _render_categories)


def handle(args: argparse.Namespace, ctx: CommandContext) -> int:
    user = ctx.resolve_user(args.user)
    if args.file_id and args.categories:
        ctx.output.error(M.ERR_FILE_CATEGORIES_WITH_DOWNLOAD)
        return 1
    if args.file_id and args.category:
        ctx.output.error(M.ERR_FILE_CATEGORY_WITH_DOWNLOAD)
        return 1

    auth_kwargs = ctx.auth_kwargs(user)
    service = ctx.services.learn

    if args.categories:
        try:
            categories = service.list_file_categories(
                user, semester=args.semester, all_terms=args.all_terms,
                course_id=args.course, allow_failure=not args.strict, **auth_kwargs,
            )
        except LearnError as e:
            ctx.output.error(M.ERR_LEARN_FAILED.format(type=type(e).__name__, message=e))
            return 1
        ctx.output.render(categories, kind="learn_file_categories")
        return 0

    if args.file_id:
        try:
            result = service.download_course_file(
                user, args.file_id, course_id=args.course,
                semester=args.semester, all_terms=args.all_terms,
                dest_dir=args.dir, allow_failure=not args.strict, **auth_kwargs,
            )
        except FileNotFoundError:
            ctx.output.error(M.ERR_FILE_NOT_FOUND.format(id=args.file_id))
            return 1
        except LearnError as e:
            ctx.output.error(M.ERR_LEARN_FAILED.format(type=type(e).__name__, message=e))
            return 1
        ctx.output.success(M.OK_DOWNLOADED.format(path=result.path))
        return 0

    try:
        listing = service.list_files(
            user, semester=args.semester, all_terms=args.all_terms,
            course_id=args.course, category_id=args.category,
            allow_failure=not args.strict, **auth_kwargs,
        )
    except LearnError as e:
        ctx.output.error(M.ERR_LEARN_FAILED.format(type=type(e).__name__, message=e))
        return 1
    ctx.output.render(listing, kind="learn_files")
    return 0
