"""argparse CLI, terminal IO, and automatic command discovery."""
from __future__ import annotations

from .main import dispatch, main  # noqa: F401  re-export

__all__ = ["dispatch", "main"]

