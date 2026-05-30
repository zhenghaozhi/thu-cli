"""Interactive shell for thu — entered when ``thu`` is invoked with no args in a TTY."""
from __future__ import annotations

import shlex
from collections.abc import Callable

from ..config import M, profiles
from .output import ui

_EXIT_COMMANDS = {"exit", "quit", "q"}


def run(dispatch: Callable[[list[str]], int]) -> int:
    try:
        import readline  # noqa: F401  enables arrow keys / history
    except ImportError:
        pass

    ui.section("thu-cli")
    ui.kv([(M.PROFILE_KEY, profiles.get_current_user() or M.NONE)])
    ui.hint(M.SHELL_HELP)
    ui.line()

    while True:
        try:
            line = input("thu> ").strip()
        except EOFError:
            ui.line()
            return 0
        except KeyboardInterrupt:
            ui.line()
            continue

        if not line:
            continue
        if line in _EXIT_COMMANDS:
            return 0
        if line == "help":
            try:
                dispatch(["--help"])
            except SystemExit:
                pass
            continue

        try:
            argv = shlex.split(line)
        except ValueError as e:
            ui.error(f"Parse error: {e}")
            continue

        if argv and argv[0] == "thu":
            argv = argv[1:]
        try:
            dispatch(argv)
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 2
            if code:
                ui.error(f"Command exited with status {code}")


__all__ = ["run"]
