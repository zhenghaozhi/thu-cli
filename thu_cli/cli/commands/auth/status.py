"""``thu auth status`` command."""
from __future__ import annotations

import argparse

from ....config import M
from ..._common import CommandContext, add_network_flags
from ...prompts import build_network

NAME = "status"
HELP = "CMD_AUTH_STATUS"


def register(subparsers: argparse._SubParsersAction) -> None:
    help_text = getattr(M, HELP)
    p = subparsers.add_parser(NAME, help=help_text, description=help_text)
    add_network_flags(p)
    p.add_argument("--user", help=M.HELP_USER)
    p.add_argument("--offline", action="store_true", help=M.HELP_OFFLINE)
    p.set_defaults(_handler=handle)


def _format_hint(kind: str, user: str | None) -> str:
    if kind == "stage_verify":
        return M.HINT_STAGE_VERIFY
    if kind == "login_force":
        return M.HINT_LOGIN_FORCE.format(user=user or M.UNKNOWN)
    if kind == "login":
        return M.HINT_LOGIN.format(user=user or M.UNKNOWN)
    return kind


def handle(args: argparse.Namespace, ctx: CommandContext) -> int:
    status = ctx.services.auth.status(
        args.user, offline=args.offline, network=build_network(args, on_event=ctx.output.emit),
    )

    if ctx.output.json_mode:
        ctx.output.render(status, kind="auth_status")
        return status.exit_code

    from ...output import ui
    ui.section(M.PROFILE)
    ui.kv([
        (M.CURRENT, status.current_user or M.NONE),
        (M.SELECTED, status.selected_user),
        (M.STUDENT_TYPE, status.student_type),
    ])
    ui.line()

    ui.section(M.LOCAL_AUTH)
    ui.kv([
        (M.DEVICE, status.device.label()),
        (M.SESSION, status.session.label()),
        (M.STAGE, status.stage.label()),
    ])
    ui.line()

    ui.section(M.REMOTE)
    ui.table(
        [M.SERVICE, M.STATUS],
        [[svc.name, svc.state.label()] for svc in status.remote_services],
    )

    if status.hint:
        ctx.output.hint(_format_hint(status.hint.kind, status.hint.user))
    return status.exit_code
