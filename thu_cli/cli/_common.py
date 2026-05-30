"""CommandContext + 命令注册协议 + 自动发现。

每个 ``cli/commands/<domain>/<cmd>.py`` 必须 expose：

    NAME: str
    HELP: str
    def register(subparsers): ...           # 加 argparse + set_defaults(_handler=handle)
    def handle(args, ctx: CommandContext) -> int

``cli/commands/<domain>/__init__.py`` 调用 ``autodiscover_commands`` 自动发现并注册
sibling 文件 — 新加命令 = 新加文件，零中心注册表。
"""
from __future__ import annotations

import argparse
import importlib
import logging
import pkgutil
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from ..config import M
from ..services.auth import AuthService
from ..services.info import InfoService
from ..services.learn import LearnService
from .output import Output
from .prompts import build_interaction, build_network, build_policy, read_user

logger = logging.getLogger("thu_cli.cli")


@dataclass
class Services:
    """单一容器，挂着所有 domain service。命令文件通过 ``ctx.services.*`` 访问。"""
    auth: AuthService
    learn: LearnService
    info: InfoService

    @classmethod
    def create(cls) -> Services:
        return cls(auth=AuthService(), learn=LearnService(), info=InfoService())


@dataclass
class CommandContext:
    """单条命令的执行上下文。

    命令文件不直接 import services / prompts / output 模块 — 全部从 ctx 拿，
    方便测试时整体替换。
    """
    services: Services
    output: Output
    args: argparse.Namespace

    def captcha_path(self, user: str | None) -> Path:
        return self.services.auth.captcha_path(user)

    def resolve_user(self, user: str | None) -> str:
        """凭据来源：``--user`` > ``$THU_USER`` > current profile > 交互。"""
        return read_user(user)

    def auth_kwargs(self, user: str | None = None) -> dict:
        """一次性 build 出 ``interaction`` / ``network`` / ``policy`` 三个 kwarg。"""
        captcha = self.captcha_path(user)
        return dict(
            interaction=build_interaction(self.args, captcha),
            network=build_network(self.args, on_event=self.output.emit),
            policy=build_policy(self.args),
        )

    def confirm_write(self, prompt: str) -> bool:
        """写操作二次确认；``--yes`` 跳过；非 tty 必须显式 ``--yes``。"""
        if getattr(self.args, "yes", False):
            return True
        if not sys.stdin.isatty():
            self.output.error(M.ERR_HOMEWORK_SUBMIT_CONFIRM)
            return False
        return self.output.confirm(prompt, default=False)


def add_network_flags(parser: argparse.ArgumentParser) -> None:
    """每条命令默认带的网络参数。

    TLS 默认校验；``--insecure`` 关闭（用于校园网抓包 / proxy MITM 场景）。
    """
    parser.add_argument("--insecure", action="store_true", help=M.HELP_INSECURE)
    parser.add_argument("--no-env-proxy", action="store_true", help=M.HELP_NO_ENV_PROXY)


def autodiscover_commands(domain_package: ModuleType, subparsers: argparse._SubParsersAction) -> int:
    """枚举 domain 包下所有 sibling 模块，调它们的 ``register()``。

    跳过 ``_``-前缀模块（私有 helper）与 ``__init__``。返回成功注册的命令数。
    """
    registered = 0
    for info in pkgutil.iter_modules(domain_package.__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{domain_package.__name__}.{info.name}")
        register = getattr(module, "register", None)
        if register is None:
            logger.debug("skip %s.%s — no register()", domain_package.__name__, info.name)
            continue
        register(subparsers)
        registered += 1
    return registered


def register_domain(
    domain_package: ModuleType,
    domain_subparsers: argparse._SubParsersAction,
    *,
    name: str,
    desc: str,
) -> bool:
    """注册一个 domain（如 auth / learn）。无任何命令时**不**注册 — 避免顶层 help
    暴露空 domain，也避免 argparse 渲染 ``choose from )`` 这种错误信息。

    返回是否实际注册了 domain。
    """
    # 先 dry-run 数命令：直接打开包里的文件名集合，避免预 import
    cmd_files = [
        info.name for info in pkgutil.iter_modules(domain_package.__path__)
        if not info.name.startswith("_")
    ]
    if not cmd_files:
        logger.debug("skip empty domain %s", name)
        return False
    p = domain_subparsers.add_parser(name, help=desc, description=desc)
    sub = p.add_subparsers(dest="cmd", metavar="<command>")
    p.set_defaults(_sub_parser=p)
    autodiscover_commands(domain_package, sub)
    return True


__all__ = [
    "CommandContext",
    "Services",
    "add_network_flags",
    "autodiscover_commands",
    "register_domain",
]
