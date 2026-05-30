"""``cli`` — argparse + 终端 IO + 自动命令发现。

入口：``thu_cli.cli.main`` （也是 ``console_scripts.thu`` 和 ``python -m thu_cli``）

每个 ``cli/commands/<domain>/<cmd>.py`` 文件遵守 4-symbol 协议：

    NAME: str                                   命令名（``thu <domain> <NAME>``）
    HELP: str                                   一行 ``--help`` 摘要
    def register(subparsers): ...               注册 argparse + 用 ``set_defaults(_handler=handle)``
    def handle(args, ctx: CommandContext) -> int

``cli/commands/<domain>/__init__.py`` 用 ``pkgutil.iter_modules`` 自动发现 sibling 文件
并调它们的 ``register()``。新加命令 = 新加文件，零中心注册表。
"""
from __future__ import annotations

from .main import dispatch, main  # noqa: F401  re-export

__all__ = ["dispatch", "main"]

