"""``thu learn homework`` command."""
from __future__ import annotations

import argparse
from pathlib import Path

from ....config import M
from ....core.errors import LearnError
from ..._common import CommandContext, add_network_flags
from ...output import register_renderer

NAME = "homework"
HELP = "CMD_LEARN_HOMEWORK"


def register(subparsers: argparse._SubParsersAction) -> None:
    help_text = getattr(M, HELP)
    p = subparsers.add_parser(NAME, help=help_text, description=help_text)
    add_network_flags(p)
    p.add_argument("homework_id", nargs="?", help=M.HELP_HOMEWORK_ID)
    p.add_argument("--user", help=M.HELP_USER)
    p.add_argument("--course", help=M.HELP_COURSE_ID)
    p.add_argument("--with-attachments", action="store_true", help=M.HELP_WITH_HOMEWORK_ATTACHMENTS)
    p.add_argument("--download", action="store_true", help=M.HELP_DOWNLOAD_HOMEWORK)
    p.add_argument("--submit", action="store_true", help=M.HELP_SUBMIT_HOMEWORK)
    p.add_argument("--yes", action="store_true", help=M.HELP_SUBMIT_YES)
    p.add_argument("--content", help=M.HELP_HOMEWORK_CONTENT)
    p.add_argument("--content-file", help=M.HELP_HOMEWORK_CONTENT_FILE)
    p.add_argument("--attach", help=M.HELP_HOMEWORK_ATTACHMENT)
    p.add_argument("--remove-attachment", action="store_true", help=M.HELP_REMOVE_HOMEWORK_ATTACHMENT)
    p.add_argument("--dir", default="downloads", help=M.HELP_DOWNLOAD_DIR)
    p.add_argument("--strict", action="store_true", help=M.HELP_STRICT)
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--all", dest="all_terms", action="store_true", help=M.HELP_ALL_TERMS)
    scope.add_argument("--semester", help=M.HELP_SEMESTER)
    p.set_defaults(_handler=handle)


def _status(item) -> str:
    if item.graded:
        return M.GRADED
    if item.submitted:
        return M.SUBMITTED
    return M.UNSUBMITTED


def _render_listing(listing, ui) -> None:
    label = M.ALL_SEMESTERS if listing.semester == "all" else listing.semester
    ui.section(M.HOMEWORKS)
    ui.kv([
        (M.PROFILE_KEY, listing.user),
        (M.SEMESTER, label),
        (M.COUNT, str(len(listing.items))),
    ])
    ui.line()
    if not listing.items:
        ui.info(M.INFO_NO_HOMEWORKS)
        return
    ui.table(
        [M.DEADLINE, M.COURSE, M.TITLE, M.STATUS, M.GRADE, M.ID],
        [
            [item.deadline, item.course_name or item.course_id, item.title,
             _status(item), item.grade or M.UNKNOWN, item.id]
            for item in listing.items
        ],
    )
    for w in listing.warnings:
        ui.warning(w.message)


def _render_detail(item, ui) -> None:
    ui.section(M.HOMEWORK)
    ui.kv([
        (M.COURSE, item.course_name or item.course_id),
        (M.TITLE, item.title),
        (M.DEADLINE, item.deadline or M.UNKNOWN),
        (M.STATUS, _status(item)),
        (M.GRADE, item.grade or M.UNKNOWN),
        (M.ID, item.id),
    ])
    files = item.downloadable_files()
    if files:
        ui.line()
        ui.section(M.ATTACHMENTS)
        for f in files:
            size = f" ({f.size})" if f.size else ""
            ui.line(f"  {f.name}{size}")
            ui.line(f"    {M.ID}: {f.id}")
            ui.line(f"    {M.DOWNLOAD_URL}: {f.download_url}")
    if item.description_text:
        ui.line()
        ui.section(M.CONTENT)
        for line in item.description_text.splitlines():
            ui.line(f"  {line}")


register_renderer("learn_homework_listing", _render_listing)
register_renderer("learn_homework_detail", _render_detail)


def _read_content(args: argparse.Namespace) -> str:
    if args.content is not None and args.content_file:
        raise ValueError(M.ERR_CONTENT_SOURCE_CONFLICT)
    if args.content_file:
        return Path(args.content_file).read_text(encoding="utf-8")
    return args.content or ""


def handle(args: argparse.Namespace, ctx: CommandContext) -> int:
    user = ctx.resolve_user(args.user)
    if args.submit and not args.homework_id:
        ctx.output.error(M.ERR_HOMEWORK_SUBMIT_NEEDS_ID)
        return 1
    if args.submit and args.download:
        ctx.output.error(M.ERR_HOMEWORK_SUBMIT_DOWNLOAD_CONFLICT)
        return 1
    if args.submit and not ctx.confirm_write(
        M.PROMPT_CONFIRM_HOMEWORK_SUBMIT.format(id=args.homework_id),
    ):
        ctx.output.warning(M.ERR_INTERRUPTED)
        return 1

    auth_kwargs = ctx.auth_kwargs(user)
    service = ctx.services.learn

    if args.homework_id and args.submit:
        try:
            content = _read_content(args)
        except ValueError as e:
            ctx.output.error(str(e))
            return 1
        try:
            result = service.submit_homework(
                user, args.homework_id,
                content=content, attachment=args.attach,
                remove_attachment=args.remove_attachment, **auth_kwargs,
            )
        except LearnError as e:
            ctx.output.error(M.ERR_LEARN_FAILED.format(type=type(e).__name__, message=e))
            return 1
        ctx.output.success(M.OK_HOMEWORK_SUBMITTED.format(id=result.homework_id))
        return 0

    if args.homework_id and args.download:
        try:
            results = service.download_homework_files(
                user, args.homework_id,
                course_id=args.course, semester=args.semester, all_terms=args.all_terms,
                dest_dir=args.dir, allow_failure=not args.strict, **auth_kwargs,
            )
        except FileNotFoundError:
            ctx.output.error(M.ERR_HOMEWORK_NOT_FOUND.format(id=args.homework_id))
            return 1
        except LearnError as e:
            ctx.output.error(M.ERR_LEARN_FAILED.format(type=type(e).__name__, message=e))
            return 1
        if not results:
            ctx.output.info(M.INFO_NO_ATTACHMENTS)
            return 0
        for result in results:
            ctx.output.success(M.OK_DOWNLOADED.format(path=result.path))
        return 0

    try:
        listing = service.list_homeworks(
            user, semester=args.semester, all_terms=args.all_terms,
            course_id=args.course,
            include_detail=bool(args.homework_id) or args.with_attachments,
            allow_failure=not args.strict, **auth_kwargs,
        )
    except LearnError as e:
        ctx.output.error(M.ERR_LEARN_FAILED.format(type=type(e).__name__, message=e))
        return 1

    if args.homework_id:
        for item in listing.items:
            if item.id == args.homework_id or item.base_id == args.homework_id:
                ctx.output.render(item, kind="learn_homework_detail")
                return 0
        ctx.output.error(M.ERR_HOMEWORK_NOT_FOUND.format(id=args.homework_id))
        return 1

    ctx.output.render(listing, kind="learn_homework_listing")
    return 0
