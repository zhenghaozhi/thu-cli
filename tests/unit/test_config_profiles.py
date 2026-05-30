"""``config.profiles`` 单元测试。"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_config_home(tmp_path: Path, monkeypatch):
    """每个测试用独立 ``THU_CLI_HOME`` 避免污染真实 profile。"""
    monkeypatch.setenv("THU_CLI_HOME", str(tmp_path))
    # profiles module 在 import 时读环境变量；需要 reload
    import importlib

    from thu_cli.config import profiles as profiles_module
    importlib.reload(profiles_module)
    yield profiles_module
    importlib.reload(profiles_module)


def test_normalize_user_basic(isolate_config_home):
    p = isolate_config_home
    assert p.normalize_user("2023012168") == "2023012168"
    assert p.normalize_user("  abc  ") == "abc"


def test_normalize_user_rejects_empty(isolate_config_home):
    p = isolate_config_home
    with pytest.raises(ValueError):
        p.normalize_user("")
    with pytest.raises(ValueError):
        p.normalize_user("   ")


def test_normalize_user_rejects_path_injection(isolate_config_home):
    p = isolate_config_home
    with pytest.raises(ValueError):
        p.normalize_user("../etc/passwd")
    with pytest.raises(ValueError):
        p.normalize_user("foo/bar")
    with pytest.raises(ValueError):
        p.normalize_user(".")


def test_add_then_remove_profile(isolate_config_home):
    p = isolate_config_home
    p.add_profile("user1")
    p.add_profile("user2", make_current=True)
    assert p.get_current_user() == "user2"
    assert set(p.list_profiles()) == {"user1", "user2"}

    p.remove_profile("user2")
    assert p.get_current_user() == "user1"
    assert p.list_profiles() == ["user1"]


def test_remove_profile_with_delete_data(isolate_config_home, tmp_path):
    p = isolate_config_home
    p.add_profile("user3", make_current=True)
    paths = p.profile_paths("user3")
    paths.session.write_text("{}", encoding="utf-8")
    assert paths.session.exists()
    p.remove_profile("user3", delete_data=True)
    assert not paths.session.exists()
    assert not paths.root.exists()


def test_remove_profile_orphan_not_deleted(isolate_config_home):
    """Regression: ``remove_profile('orphan', delete_data=True)`` 必须**不**删未注册的孤立目录。"""
    p = isolate_config_home
    paths = p.profile_paths("orphan")
    paths.root.mkdir(parents=True)
    sentinel = paths.root / "important.txt"
    sentinel.write_text("not registered, must keep")
    assert "orphan" not in p.list_profiles()
    result = p.remove_profile("orphan", delete_data=True)
    assert result is False
    assert paths.root.exists()
    assert sentinel.exists()


def test_student_type_default_undergraduate(isolate_config_home):
    p = isolate_config_home
    p.add_profile("u1")
    assert p.get_student_type("u1") == "undergraduate"


def test_student_type_persist(isolate_config_home):
    p = isolate_config_home
    p.add_profile("u1")
    p.set_student_type("u1", "graduate")
    assert p.get_student_type("u1") == "graduate"


def test_student_type_invalid_raises(isolate_config_home):
    p = isolate_config_home
    p.add_profile("u1")
    with pytest.raises(ValueError):
        p.set_student_type("u1", "bogus")


def test_resolve_user_arg(isolate_config_home):
    p = isolate_config_home
    assert p.resolve_user("u1") == "u1"


def test_resolve_user_falls_back_to_current(isolate_config_home):
    p = isolate_config_home
    p.add_profile("u2", make_current=True)
    assert p.resolve_user(None) == "u2"


def test_resolve_user_no_current_returns_none(isolate_config_home):
    p = isolate_config_home
    assert p.resolve_user(None) is None
