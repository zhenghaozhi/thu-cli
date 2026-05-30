"""``thu campus`` placeholder domain registration."""
from __future__ import annotations

import argparse
import sys

from ....config import M
from ..._common import register_domain

DESC = "CAMPUS_DESC"


def register_root(domain_subparsers: argparse._SubParsersAction) -> bool:
    return register_domain(sys.modules[__name__], domain_subparsers,
                           name="campus", desc=getattr(M, DESC))
