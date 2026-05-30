"""``thu info transcript`` — 历年成绩单 + GPA 汇总。"""
from __future__ import annotations

import argparse

from ....config import M
from ..._common import CommandContext, add_network_flags
from ...output import register_renderer

NAME = "transcript"
HELP = "历年成绩单 + 官方/明细 GPA"


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(NAME, help=HELP, description=HELP)
    add_network_flags(p)
    p.add_argument("--user", help=M.HELP_USER)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--graduate", action="store_true", help=M.HELP_GRADUATE)
    g.add_argument("--undergraduate", action="store_true", help=M.HELP_UNDERGRADUATE)
    p.set_defaults(_handler=handle)


def _fmt(v: float | None, *, digits: int = 3) -> str:
    return M.UNKNOWN if v is None else f"{v:.{digits}f}"


def _render(transcript, ui) -> None:
    ui.section(M.TRANSCRIPT)
    if not transcript.courses:
        ui.info(M.INFO_NO_TRANSCRIPT)
        return
    rows = [
        [c.course_code, c.semester, c.name, f"{c.credit:g}", c.grade, f"{c.point:g}"]
        for c in transcript.courses
    ]
    ui.table([M.COURSE_CODE, M.SEMESTER, M.COURSE, M.CREDIT, M.GRADE, M.POINT], rows)
    summary = transcript.summary
    ui.line()
    ui.kv([
        (M.COURSE_COUNT, str(summary.course_count)),
        (M.OFFICIAL_TOTAL, _fmt(summary.official_total_credit, digits=1)),
        (M.DETAIL_TOTAL, f"{summary.total_credit:g}"),
        (M.GPA_CREDIT, f"{summary.gpa_credit:g}"),
        (M.OFFICIAL_GPA, _fmt(summary.official_gpa)),
        (M.CALC_GPA, _fmt(summary.calculated_gpa)),
    ])


register_renderer("info_transcript", _render)


def handle(args: argparse.Namespace, ctx: CommandContext) -> int:
    user = ctx.resolve_user(args.user)
    graduate: bool | None = None
    if args.graduate:
        graduate = True
    elif args.undergraduate:
        graduate = False
    transcript = ctx.services.info.get_transcript_detail(
        user, graduate=graduate, **ctx.auth_kwargs(user),
    )
    ctx.output.render(transcript, kind="info_transcript")
    return 0
