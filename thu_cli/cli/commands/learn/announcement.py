"""``thu learn announcement`` command."""
from __future__ import annotations

import argparse

from ....config import M
from ....core.errors import LearnError
from ..._common import CommandContext, add_network_flags
from ...output import register_renderer

NAME = "announcement"
HELP = "CMD_LEARN_ANNOUNCEMENT"


def register(subparsers: argparse._SubParsersAction) -> None:
    help_text = getattr(M, HELP)
    p = subparsers.add_parser(NAME, help=help_text, description=help_text)
    add_network_flags(p)
    p.add_argument("announcement_id", nargs="?", help=M.HELP_ANNOUNCEMENT_ID)
    p.add_argument("--user", help=M.HELP_USER)
    p.add_argument("--course", help=M.HELP_COURSE_ID)
    p.add_argument("--unread", action="store_true", help=M.HELP_UNREAD_ONLY)
    p.add_argument("--strict", action="store_true", help=M.HELP_STRICT)
    p.add_argument("--with-attachments", action="store_true", help=M.HELP_WITH_ATTACHMENTS)
    p.add_argument("--download-attachments", action="store_true", help=M.HELP_DOWNLOAD_ATTACHMENTS)
    p.add_argument("--dir", default="downloads", help=M.HELP_DOWNLOAD_DIR)
    scope = p.add_mutually_exclusive_group()
    scope.add_argument("--all", dest="all_terms", action="store_true", help=M.HELP_ALL_TERMS)
    scope.add_argument("--semester", help=M.HELP_SEMESTER)
    p.set_defaults(_handler=handle)


def _flag(value: bool | None) -> str:
    if value is None:
        return M.UNKNOWN
    return M.YES if value else M.NO


def _render_listing(listing, ui) -> None:
    label = M.ALL_SEMESTERS if listing.semester == "all" else listing.semester
    ui.section(M.ANNOUNCEMENTS)
    ui.kv([
        (M.PROFILE_KEY, listing.user),
        (M.SEMESTER, label),
        (M.COUNT, str(len(listing.items))),
    ])
    ui.line()
    if not listing.items:
        ui.info(M.INFO_NO_ANNOUNCEMENTS)
        return
    ui.table(
        [M.PUBLISHED_AT, M.COURSE, M.TITLE, M.UNREAD, M.ID],
        [
            [item.published_at, item.course_name or item.course_id,
             item.title, _flag(item.unread), item.id]
            for item in listing.items
        ],
    )
    for w in listing.warnings:
        ui.warning(w.message)


def _render_detail(detail, ui) -> None:
    if not detail.announcement:
        ui.error(M.ERR_ANNOUNCEMENT_NOT_FOUND.format(id="<unknown>"))
        return
    a = detail.announcement
    label = M.ALL_SEMESTERS if detail.semester == "all" else detail.semester
    ui.section(M.ANNOUNCEMENT)
    ui.kv([
        (M.PROFILE_KEY, detail.user),
        (M.SEMESTER, label),
        (M.COURSE, a.course_name or a.course_id),
        (M.TITLE, a.title),
        (M.PUBLISHER, a.publisher or M.UNKNOWN),
        (M.PUBLISHED_AT, a.published_at or M.UNKNOWN),
        (M.UNREAD, _flag(a.unread)),
        (M.IMPORTANT, _flag(a.important)),
        (M.EXPIRED, _flag(a.expired)),
        (M.ID, a.id),
    ])
    if a.attachments:
        ui.line()
        ui.section(M.ATTACHMENTS)
        for item in a.attachments:
            size = f" ({item.size})" if item.size else ""
            ui.line(f"  {item.name}{size}")
            ui.line(f"    {M.ID}: {item.id}")
            ui.line(f"    {M.DOWNLOAD_URL}: {item.download_url}")
            ui.line(f"    {M.PREVIEW_URL}: {item.preview_url}")
    elif a.attachment_names:
        ui.line()
        ui.section(M.ATTACHMENTS)
        for name in a.attachment_names:
            ui.line(f"  {name}")
    if a.content_text:
        ui.line()
        ui.section(M.CONTENT)
        for line in a.content_text.splitlines():
            ui.line(f"  {line}")
    for w in detail.warnings:
        ui.warning(w.message)


register_renderer("learn_announcement_listing", _render_listing)
register_renderer("learn_announcement_detail", _render_detail)


def handle(args: argparse.Namespace, ctx: CommandContext) -> int:
    user = ctx.resolve_user(args.user)
    auth_kwargs = ctx.auth_kwargs(user)
    service = ctx.services.learn

    if args.announcement_id and args.download_attachments:
        try:
            results = service.download_announcement_attachments(
                user, args.announcement_id,
                course_id=args.course, semester=args.semester, all_terms=args.all_terms,
                dest_dir=args.dir, allow_failure=not args.strict, **auth_kwargs,
            )
        except FileNotFoundError:
            ctx.output.error(M.ERR_ANNOUNCEMENT_NOT_FOUND.format(id=args.announcement_id))
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

    if args.announcement_id:
        try:
            detail = service.get_announcement(
                user, args.announcement_id,
                semester=args.semester, all_terms=args.all_terms,
                course_id=args.course, include_attachments=args.with_attachments,
                allow_failure=not args.strict, **auth_kwargs,
            )
        except LearnError as e:
            ctx.output.error(M.ERR_LEARN_FAILED.format(type=type(e).__name__, message=e))
            return 1
        if not detail.announcement:
            ctx.output.error(M.ERR_ANNOUNCEMENT_NOT_FOUND.format(id=args.announcement_id))
            for w in detail.warnings:
                ctx.output.warning(w.message)
            return 1
        ctx.output.render(detail, kind="learn_announcement_detail")
        return 0

    try:
        listing = service.list_announcements(
            user, semester=args.semester, all_terms=args.all_terms,
            course_id=args.course, unread_only=args.unread,
            allow_failure=not args.strict, **auth_kwargs,
        )
    except LearnError as e:
        ctx.output.error(M.ERR_LEARN_FAILED.format(type=type(e).__name__, message=e))
        return 1
    ctx.output.render(listing, kind="learn_announcement_listing")
    return 0
