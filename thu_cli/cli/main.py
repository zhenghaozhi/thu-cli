"""Root entry point for the ``thu`` command."""
from __future__ import annotations

import argparse
import importlib
import logging
import os
import pkgutil
import sys

from ..config import M
from ..core.errors import AuthError, BadCredentials, CaptchaRequired, ThuCliError, TwoFactorFailed
from . import commands as commands_pkg
from ._common import CommandContext, Services
from .output import Output, to_json, ui


def _discover_domain_packages() -> list[str]:
    return sorted(
        info.name
        for info in pkgutil.iter_modules(commands_pkg.__path__)
        if info.ispkg and not info.name.startswith("_")
    )


def _configure_logging(*, verbose: bool = False) -> None:
    """Enable protocol-level traces with ``THU_CLI_LOG=DEBUG`` or ``-v``."""
    level_name = "DEBUG" if verbose else os.environ.get("THU_CLI_LOG", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(name)s %(levelname)s %(message)s",
            stream=sys.stderr,
        )
    else:
        logging.getLogger().setLevel(level)


def _build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="thu", description=M.APP_DESC)
    ap.add_argument("-v", "--verbose", action="store_true", help=M.HELP_VERBOSE)
    ap.add_argument("--json", action="store_true", help=M.HELP_JSON)
    domain_sub = ap.add_subparsers(dest="domain", metavar="<domain>")
    for name in _discover_domain_packages():
        module = importlib.import_module(f"thu_cli.cli.commands.{name}")
        register_root = module.register_root
        register_root(domain_sub)
    return ap


def dispatch(argv: list[str]) -> int:
    parser = _build_argparser()
    args = parser.parse_args(argv)
    _configure_logging(verbose=getattr(args, "verbose", False))

    if args.domain is None:
        parser.print_help()
        return 0

    handler = getattr(args, "_handler", None)
    if handler is None:
        sub_parser = getattr(args, "_sub_parser", None)
        if sub_parser is not None:
            sub_parser.print_help()
            return 0
        parser.error(f"no command for domain {args.domain!r}")
        return 2

    ctx = CommandContext(
        services=Services.create(),
        output=Output(json_mode=getattr(args, "json", False)),
        args=args,
    )

    try:
        return int(handler(args, ctx))
    except ThuCliError as e:
        return _print_thu_error(e, json_mode=ctx.output.json_mode)
    except FileNotFoundError as e:
        _print_generic_error(e, json_mode=ctx.output.json_mode, exit_code=1)
        return 1
    except ValueError as e:
        _print_generic_error(e, json_mode=ctx.output.json_mode, exit_code=1)
        return 1


def _print_thu_error(e: ThuCliError, *, json_mode: bool) -> int:
    """Print one top-level ``ThuCliError`` in JSON or human mode."""
    if isinstance(e, BadCredentials):
        msg = M.ERR_BAD_CREDENTIALS.format(message=e)
        rc = 2
    elif isinstance(e, TwoFactorFailed):
        msg = M.ERR_2FA_FAILED.format(message=e)
        rc = 2
    elif isinstance(e, CaptchaRequired):
        msg = M.ERR_CAPTCHA_REQUIRED.format(message=e)
        rc = 2
    elif isinstance(e, AuthError):
        msg = M.ERR_AUTH_FAILED.format(type=type(e).__name__, message=e)
        rc = 2
    else:
        msg = f"{type(e).__name__}: {e}"
        rc = 1
    _emit_error(type(e).__name__, str(e), msg, json_mode=json_mode)
    return rc


def _print_generic_error(e: Exception, *, json_mode: bool, exit_code: int) -> None:
    _emit_error(type(e).__name__, str(e), str(e), json_mode=json_mode)


def _emit_error(error_type: str, raw_message: str, human_message: str, *, json_mode: bool) -> None:
    if json_mode:
        print(to_json({"error": {"type": error_type, "message": raw_message}}), file=sys.stderr)
    else:
        ui.error(human_message)


def main(argv: list[str] | None = None, *, interactive: bool = True) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        _configure_logging()
        if interactive and sys.stdin.isatty() and sys.stdout.isatty():
            from .shell import run as shell_run
            return shell_run(dispatch)
        _build_argparser().print_help()
        return 0
    try:
        return dispatch(argv)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    except KeyboardInterrupt:
        ui.error(M.ERR_INTERRUPTED)
        return 130


__all__ = ["dispatch", "main"]
