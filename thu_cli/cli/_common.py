"""Command context, command registration, and module discovery."""
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
    """Container for domain services available to command handlers."""
    auth: AuthService
    learn: LearnService
    info: InfoService

    @classmethod
    def create(cls) -> Services:
        return cls(auth=AuthService(), learn=LearnService(), info=InfoService())


@dataclass
class CommandContext:
    """Execution context passed to one command handler."""
    services: Services
    output: Output
    args: argparse.Namespace

    def captcha_path(self, user: str | None) -> Path:
        return self.services.auth.captcha_path(user)

    def resolve_user(self, user: str | None) -> str:
        """Resolve user from ``--user`` > ``$THU_USER`` > current profile > prompt."""
        return read_user(user)

    def auth_kwargs(self, user: str | None = None) -> dict:
        """Build ``interaction``, ``network``, and ``policy`` kwargs."""
        captcha = self.captcha_path(user)
        return dict(
            interaction=build_interaction(self.args, captcha),
            network=build_network(self.args, on_event=self.output.emit),
            policy=build_policy(self.args),
        )

    def confirm_write(self, prompt: str) -> bool:
        """Confirm a write operation unless ``--yes`` is present."""
        if getattr(self.args, "yes", False):
            return True
        if not sys.stdin.isatty():
            self.output.error(M.ERR_HOMEWORK_SUBMIT_CONFIRM)
            return False
        return self.output.confirm(prompt, default=False)


def add_network_flags(parser: argparse.ArgumentParser) -> None:
    """Add network flags shared by every remote command."""
    parser.add_argument("--insecure", action="store_true", help=M.HELP_INSECURE)
    parser.add_argument("--no-env-proxy", action="store_true", help=M.HELP_NO_ENV_PROXY)


def autodiscover_commands(domain_package: ModuleType, subparsers: argparse._SubParsersAction) -> int:
    """Register sibling command modules in a domain package."""
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
    """Register a domain only when it contains command modules."""
    # Count command files first to avoid pre-importing empty domains.
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
