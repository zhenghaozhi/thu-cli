"""``thu campus`` 域 — 占位。

预留扩展位：电费 / 网费 / 图书馆 / 校园卡 / 教室占用。当前无任何命令文件，所以
``register_root`` 返回 False，**顶层 help 不会显示此 domain**（``register_domain``
对空 domain 跳过注册，避免 argparse 渲染 ``choose from )`` 这种半成品错误信息）。

加新命令时只需在本目录 drop ``<cmd>.py``，遵守 NAME / HELP / register / handle 协议。
"""
from __future__ import annotations

import argparse
import sys

from ....config import M
from ..._common import register_domain

DESC = M.CAMPUS_DESC


def register_root(domain_subparsers: argparse._SubParsersAction) -> bool:
    return register_domain(sys.modules[__name__], domain_subparsers,
                           name="campus", desc=DESC)
