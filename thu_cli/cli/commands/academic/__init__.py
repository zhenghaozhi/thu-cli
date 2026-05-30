"""``thu academic`` 域 — 占位。

预留扩展位：培养方案 / 考试 / 窥分。当前无任何命令文件，所以 ``register_root``
返回 False，**顶层 help 不会显示此 domain**。

加新命令时只需在本目录 drop ``<cmd>.py``，遵守 NAME / HELP / register / handle 协议。
"""
from __future__ import annotations

import argparse
import sys

from ....config import M
from ..._common import register_domain

DESC = M.ACADEMIC_DESC


def register_root(domain_subparsers: argparse._SubParsersAction) -> bool:
    return register_domain(sys.modules[__name__], domain_subparsers,
                           name="academic", desc=DESC)
