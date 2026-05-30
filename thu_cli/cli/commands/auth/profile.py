"""``thu auth profile`` — 多 profile 管理。子动作：``list`` / ``add`` / ``remove``。

不带子动作时等价 ``list``。
"""
from __future__ import annotations

import argparse

from ....config import M
from ..._common import CommandContext

NAME = "profile"
HELP = "管理本地账号 profile（list / add / remove）"


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(NAME, help=HELP, description=HELP)
    sub = p.add_subparsers(dest="profile_cmd")
    sub.add_parser("list", help="列出 profiles")

    q = sub.add_parser("add", help="新增 profile")
    q.add_argument("user")
    q.add_argument("--current", action="store_true", help=M.HELP_PROFILE_CURRENT)
    q.add_argument("--student-type", choices=["undergraduate", "graduate"],
                   default=None, dest="student_type", help=M.HELP_STUDENT_TYPE)

    q = sub.add_parser("remove", help="删除 profile")
    q.add_argument("user")
    q.add_argument("--delete-data", action="store_true", help=M.HELP_PROFILE_DELETE_DATA)

    p.set_defaults(_handler=handle)


def handle(args: argparse.Namespace, ctx: CommandContext) -> int:
    cmd = args.profile_cmd or "list"

    if cmd == "add":
        try:
            user = ctx.services.auth.add_profile(args.user, make_current=args.current)
        except ValueError as e:
            ctx.output.error(M.ERR_INVALID_PROFILE.format(detail=e))
            return 1
        if args.student_type:
            try:
                ctx.services.auth.set_student_type(user, args.student_type)
            except ValueError as e:
                ctx.output.warning(f"student-type 未保存：{e}")
        ctx.output.success(M.OK_PROFILE_ADDED.format(user=user))
        if ctx.services.auth.current_user() == user:
            ctx.output.hint(M.OK_PROFILE_CURRENT.format(user=user))
        return 0

    if cmd == "remove":
        try:
            removed = ctx.services.auth.remove_profile(args.user, delete_data=args.delete_data)
        except ValueError as e:
            ctx.output.error(M.ERR_INVALID_PROFILE.format(detail=e))
            return 1
        if not removed:
            ctx.output.warning(M.WARN_PROFILE_NOT_FOUND.format(user=args.user))
            return 1
        ctx.output.success(M.OK_PROFILE_REMOVED.format(user=args.user))
        ctx.output.hint(M.OK_PROFILE_CURRENT.format(
            user=ctx.services.auth.current_user() or M.NONE,
        ))
        return 0

    # list
    rows = ctx.services.auth.profile_rows()
    if ctx.output.json_mode:
        ctx.output.render(rows, kind="profile_rows")
        return 0
    if not rows:
        ctx.output.info(M.INFO_NO_PROFILES)
        ctx.output.hint(M.HINT_PROFILE_ADD)
        return 0

    from ...output import ui
    ui.table(
        [M.CURRENT, M.USER, M.STUDENT_TYPE, M.SESSION, M.DEVICE, M.STAGE],
        [
            [
                "*" if row.current else "",
                row.user,
                row.student_type,
                row.session.label(),
                row.device.label(),
                row.stage.label(),
            ]
            for row in rows
        ],
    )
    return 0
