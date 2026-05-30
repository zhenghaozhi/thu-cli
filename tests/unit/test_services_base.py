"""Unit tests for service base helpers."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from thu_cli.core.errors import SessionExpired
from thu_cli.sdk.learn import Course
from thu_cli.services.base import CourseScopedListing, Listing, ServiceWarning


def test_listing_default_warnings_empty():
    listing = Listing(user="x", items=[1, 2, 3])
    assert listing.warnings == []


def test_course_scoped_listing_by_course():
    @dataclass
    class Item:
        course_id: str
        title: str

    courses = [
        Course(id="c1", semester_id="s", code="", class_no="", name="C1",
               english_name="", teacher="", schedule="", raw={}),
        Course(id="c2", semester_id="s", code="", class_no="", name="C2",
               english_name="", teacher="", schedule="", raw={}),
    ]
    listing = CourseScopedListing(
        user="x", semester="s", courses=courses,
        items=[Item("c1", "a"), Item("c2", "b"), Item("c1", "c")],
    )
    grouped = listing.by_course()
    assert len(grouped["c1"]) == 2
    assert len(grouped["c2"]) == 1


def test_course_scoped_listing_course_by_id():
    courses = [
        Course(id=f"c{i}", semester_id="s", code="", class_no="", name=f"C{i}",
               english_name="", teacher="", schedule="", raw={})
        for i in range(3)
    ]
    listing = CourseScopedListing(user="x", semester="s", courses=courses, items=[])
    by_id = listing.course_by_id()
    assert set(by_id) == {"c0", "c1", "c2"}


def test_course_scoped_listing_as_listing():
    courses = [Course(id="c1", semester_id="s", code="", class_no="", name="",
                      english_name="", teacher="", schedule="", raw={})]
    cs = CourseScopedListing(user="u", semester="s", courses=courses,
                             items=[1, 2], warnings=[ServiceWarning("x", "y")])
    plain = cs.as_listing()
    assert plain.user == "u"
    assert plain.items == [1, 2]
    assert plain.warnings[0].context == "x"

def test_with_reauth_no_retry_on_success():
    from thu_cli.services.base import BaseService
    base = BaseService()
    calls = []

    def call(force_login: bool):
        calls.append(force_login)
        return "ok"

    assert base.with_reauth(call) == "ok"
    assert calls == [False]


def test_with_reauth_retries_once_on_session_expired():
    from thu_cli.services.base import BaseService
    base = BaseService()
    calls = []

    def call(force_login: bool):
        calls.append(force_login)
        if not force_login:
            raise SessionExpired("expired")
        return "ok"

    assert base.with_reauth(call) == "ok"
    assert calls == [False, True]


def test_with_reauth_safe_to_retry_false_does_not_retry():
    from thu_cli.services.base import BaseService
    base = BaseService()
    calls = []

    def call(force_login: bool):
        calls.append(force_login)
        raise SessionExpired("expired")

    with pytest.raises(SessionExpired):
        base.with_reauth(call, safe_to_retry=False)
    assert calls == [False]

def test_fanout_parallel_collects_results():
    from thu_cli.services.base import BaseService
    base = BaseService()
    entities = ["a", "b", "c"]
    items, warnings = base.fanout_parallel(
        entities,
        lambda e: [e, e + "!"],
        context_of=lambda e: e,
    )
    assert sorted(items) == ["a", "a!", "b", "b!", "c", "c!"]
    assert warnings == []


def test_fanout_parallel_collects_warnings_on_failure():
    from thu_cli.services.base import BaseService
    base = BaseService()

    def fetch(e: str) -> list:
        if e == "bad":
            raise RuntimeError("boom")
        return [e]

    items, warnings = base.fanout_parallel(
        ["a", "bad", "c"],
        fetch,
        context_of=lambda e: e,
        label_of=lambda e: f"course {e}",
    )
    assert sorted(items) == ["a", "c"]
    assert len(warnings) == 1
    assert warnings[0].context == "bad"
    assert "course bad" in warnings[0].message


def test_fanout_parallel_session_expired_propagates():
    from thu_cli.services.base import BaseService
    base = BaseService()

    def fetch(e: str) -> list:
        raise SessionExpired("expired")

    with pytest.raises(SessionExpired):
        base.fanout_parallel(["a"], fetch, context_of=lambda e: e)


def test_fanout_parallel_strict_mode_raises():
    from thu_cli.services.base import BaseService
    base = BaseService()

    def fetch(e: str) -> list:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        base.fanout_parallel(["a"], fetch, context_of=lambda e: e, allow_failure=False)
