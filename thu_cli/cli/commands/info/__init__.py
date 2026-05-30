"""``thu info`` 域。命令自动发现；空 domain 不注册。"""
from __future__ import annotations

import argparse
import sys

from ....config import M
from ..._common import register_domain

DESC = M.INFO_DESC


def register_root(domain_subparsers: argparse._SubParsersAction) -> bool:
    return register_domain(sys.modules[__name__], domain_subparsers,
                           name="info", desc=DESC)
