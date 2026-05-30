"""Architecture invariants.

These tests pin the layered architecture by parsing import statements with the
``ast`` module and asserting which packages may depend on which. They run
without network and without auth, so they catch layer violations on every
``pytest`` invocation.

Layers (allowed import direction):
    core  ← sdk  ← services  ← cli
                   ↑
                  config (only sdk-independent helpers / paths / i18n)

Forbidden:
    core    importing sdk / services / config / cli
    sdk     importing services / config / cli
    services importing cli
    cli     importing nothing forbidden (it's the top layer)
"""
from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path

import pytest

import thu_cli

PKG_ROOT = Path(thu_cli.__file__).parent


def _all_modules(package_name: str) -> list[str]:
    """所有 ``package_name`` 包下的 module fully-qualified names。"""
    package = importlib.import_module(package_name)
    out = [package_name]
    for info in pkgutil.walk_packages(package.__path__, prefix=package_name + "."):
        out.append(info.name)
    return out


def _imports_of(module_name: str) -> set[str]:
    """parse ``module_name``，返回所有 ``from X import Y`` / ``import X`` 中的 X 顶级路径。"""
    module = importlib.import_module(module_name)
    if not hasattr(module, "__file__") or module.__file__ is None:
        return set()
    src = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src, filename=module.__file__)
    imports: set[str] = set()
    pkg_root = module_name.rsplit(".", 1)[0] if "." in module_name else module_name
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    imports.add(node.module)
            else:
                # 相对 import：用 module 自身的 package 路径解析
                parts = pkg_root.split(".")
                # node.level 是 leading-dot 数。如 from ...config import M from
                # thu_cli.cli.commands.auth.login → level=4 → go up 3 → thu_cli
                base = parts[: -(node.level - 1)] if node.level > 1 else parts
                resolved = ".".join(base + ([node.module] if node.module else []))
                imports.add(resolved)
    return imports


def _has_forbidden_import(module_name: str, forbidden_prefixes: tuple[str, ...]) -> str | None:
    for imp in _imports_of(module_name):
        for prefix in forbidden_prefixes:
            if imp == prefix or imp.startswith(prefix + "."):
                return imp
    return None


# ============================================================================
# Layer tests
# ============================================================================
def test_core_does_not_depend_on_higher_layers():
    forbidden = ("thu_cli.sdk", "thu_cli.services", "thu_cli.config", "thu_cli.cli")
    for module in _all_modules("thu_cli.core"):
        bad = _has_forbidden_import(module, forbidden)
        assert bad is None, f"{module} imports {bad!r}; core must be free of higher layers"


def test_sdk_does_not_depend_on_services_config_cli():
    """sdk 层是 SDK 用户的最小子集；不允许依赖 services/config/cli。

    这一条是 "热插拔" 承诺的关键：拷走 ``core/`` + ``sdk/`` 就能独立跑。
    """
    forbidden = ("thu_cli.services", "thu_cli.config", "thu_cli.cli")
    for module in _all_modules("thu_cli.sdk"):
        bad = _has_forbidden_import(module, forbidden)
        assert bad is None, (
            f"{module} imports {bad!r}; sdk layer must not depend on services/config/cli. "
            f"This breaks the minimal-subset extraction guarantee."
        )


def test_services_does_not_depend_on_cli():
    forbidden = ("thu_cli.cli",)
    for module in _all_modules("thu_cli.services"):
        bad = _has_forbidden_import(module, forbidden)
        assert bad is None, f"{module} imports {bad!r}; services must not depend on cli"


def test_config_does_not_depend_on_sdk_services_cli():
    """config 是叶子层（只供 cli / services 用）；不能反过来依赖它们。"""
    forbidden = ("thu_cli.sdk", "thu_cli.services", "thu_cli.cli")
    for module in _all_modules("thu_cli.config"):
        bad = _has_forbidden_import(module, forbidden)
        assert bad is None, f"{module} imports {bad!r}; config must not depend on higher layers"


# ============================================================================
# CLI command file 协议
# ============================================================================
def _command_modules() -> list[str]:
    """所有 cli/commands/<domain>/<cmd>.py（不含 __init__ / _xxx）。"""
    out = []
    for domain_dir in (PKG_ROOT / "cli" / "commands").iterdir():
        if not domain_dir.is_dir():
            continue
        for py in domain_dir.iterdir():
            if py.suffix != ".py":
                continue
            if py.stem.startswith("_"):
                continue
            out.append(f"thu_cli.cli.commands.{domain_dir.name}.{py.stem}")
    return out


@pytest.mark.parametrize("module_name", _command_modules())
def test_command_file_exposes_register_and_handle(module_name: str):
    """每个命令文件必须 expose ``NAME``, ``HELP``, ``register``, ``handle``。"""
    module = importlib.import_module(module_name)
    for attr in ("NAME", "HELP", "register", "handle"):
        assert hasattr(module, attr), f"{module_name} missing {attr!r}"
    assert isinstance(module.NAME, str) and module.NAME, f"{module_name}.NAME must be non-empty str"
    assert isinstance(module.HELP, str) and module.HELP, f"{module_name}.HELP must be non-empty str"
    assert callable(module.register), f"{module_name}.register must be callable"
    assert callable(module.handle), f"{module_name}.handle must be callable"


# ============================================================================
# 命令文件不应自己构造 AuthInteraction（必须走 cli.prompts）
# ============================================================================
@pytest.mark.parametrize("module_name", _command_modules())
def test_command_file_does_not_build_auth_interaction(module_name: str):
    """避免每个命令文件重复 14-kwarg fanout：必须通过 ``cli.prompts.build_interaction``。"""
    module = importlib.import_module(module_name)
    if not hasattr(module, "__file__") or module.__file__ is None:
        return
    src = Path(module.__file__).read_text(encoding="utf-8")
    assert "AuthInteraction(" not in src, (
        f"{module_name} constructs AuthInteraction directly; use ctx.auth_kwargs() "
        f"or cli.prompts.build_interaction() instead"
    )
