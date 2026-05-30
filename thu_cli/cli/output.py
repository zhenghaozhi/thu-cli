"""Terminal UI primitives and the command output entry point."""
from __future__ import annotations

import getpass
import json
import os
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, is_dataclass
from typing import Any

from ..config import M

_COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "cyan": "\033[36m",
}


def _color_enabled(stream: object) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return bool(getattr(stream, "isatty", lambda: False)())


@dataclass
class UI:
    color: bool | None = None

    def _use_color(self, stream: object | None = None) -> bool:
        stream = sys.stdout if stream is None else stream
        return _color_enabled(stream) if self.color is None else self.color

    def style(self, text: str, *names: str, stream: object | None = None) -> str:
        if not self._use_color(stream):
            return text
        prefix = "".join(_COLORS[n] for n in names if n in _COLORS)
        return f"{prefix}{text}{_COLORS['reset']}" if prefix else text

    def tag(self, name: str, color: str, *, stream: object | None = None) -> str:
        return self.style(f"[{name}]", color, "bold", stream=stream)

    def line(self, text: str = "", *, stream: object | None = None) -> None:
        stream = sys.stdout if stream is None else stream
        print(text, file=stream)

    def info(self, message: str) -> None:
        self.line(f"{self.tag('info', 'blue')} {message}")

    def success(self, message: str) -> None:
        self.line(f"{self.tag('success', 'green')} {message}")

    def warning(self, message: str) -> None:
        self.line(
            f"{self.tag('warning', 'yellow', stream=sys.stderr)} {message}",
            stream=sys.stderr,
        )

    def error(self, message: str) -> None:
        self.line(
            f"{self.tag('error', 'red', stream=sys.stderr)} {message}",
            stream=sys.stderr,
        )

    def emit(self, level: str, message: str) -> None:
        """Dispatch an event level to the matching UI method."""
        {"success": self.success, "warning": self.warning, "error": self.error}.get(
            level, self.info,
        )(message)

    def hint(self, message: str, *, stream: object | None = None) -> None:
        stream = sys.stdout if stream is None else stream
        self.line(f"{self.tag('hint', 'cyan', stream=stream)} {message}", stream=stream)

    def section(self, title: str) -> None:
        self.line(self.style(title, "bold"))

    def kv(self, rows: Sequence[tuple[str, str]], *, indent: int = 2) -> None:
        if not rows:
            return
        width = max(len(k) for k, _ in rows)
        pad = " " * indent
        for key, value in rows:
            self.line(f"{pad}{key:<{width}}  {value}")

    def table(self, headers: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
        rows = [[str(cell) for cell in row] for row in rows]
        headers = [str(h) for h in headers]
        if not rows:
            self.line("(empty)")
            return
        widths = [len(h) for h in headers]
        for row in rows:
            for idx, cell in enumerate(row):
                widths[idx] = max(widths[idx], len(cell))
        header = "  ".join(h.ljust(widths[idx]) for idx, h in enumerate(headers))
        self.line(self.style(header, "bold"))
        self.line(self.style("  ".join("-" * w for w in widths), "dim"))
        for row in rows:
            self.line("  ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(row)))

    def prompt(self, label: str) -> str:
        return input(f"{label}: ").strip()

    def secret(self, label: str) -> str:
        return getpass.getpass(f"{label}: ")

    def confirm(self, message: str, *, default: bool = False) -> bool:
        suffix = "[Y/n]" if default else "[y/N]"
        while True:
            answer = input(f"{message} {suffix} ").strip().lower()
            if not answer:
                return default
            if answer in {"y", "yes", M.YES.lower()}:
                return True
            if answer in {"n", "no", M.NO.lower()}:
                return False


ui = UI()

def _to_jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f: _to_jsonable(getattr(obj, f)) for f in obj.__dataclass_fields__}
    return str(obj)


def to_json(obj: Any) -> str:
    return json.dumps(_to_jsonable(obj), ensure_ascii=False, indent=2)

Renderer = Callable[[Any, UI], None]
_RENDERERS: dict[str, Renderer] = {}


def register_renderer(kind: str, fn: Renderer) -> None:
    _RENDERERS[kind] = fn

@dataclass
class Output:
    """Output object exposed to command handlers."""
    json_mode: bool = False

    def render(self, data: Any, *, kind: str) -> None:
        if self.json_mode:
            print(to_json(data))
            return
        renderer = _RENDERERS.get(kind)
        if renderer is None:
            ui.warning(f"no renderer for kind={kind!r}; falling back to JSON")
            print(to_json(data))
            return
        renderer(data, ui)

    def info(self, msg: str) -> None: ui.info(msg)
    def success(self, msg: str) -> None: ui.success(msg)
    def warning(self, msg: str) -> None: ui.warning(msg)
    def error(self, msg: str) -> None: ui.error(msg)
    def hint(self, msg: str) -> None: ui.hint(msg)
    def emit(self, level: str, msg: str) -> None: ui.emit(level, msg)
    def confirm(self, msg: str, *, default: bool = False) -> bool:
        return ui.confirm(msg, default=default)


__all__ = [
    "Output",
    "Renderer",
    "UI",
    "register_renderer",
    "to_json",
    "ui",
]
