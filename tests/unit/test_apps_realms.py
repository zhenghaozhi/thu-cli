"""Unit tests for ``core.realms`` and ``core.apps``."""
from __future__ import annotations

import pytest

from thu_cli.core.apps import (
    CAMPUS_APPS,
    INFO_PORTAL,
    TIMETABLE_BKS,
    TIMETABLE_YJS,
    TRANSCRIPT_BKS,
    TRANSCRIPT_YJS,
)
from thu_cli.core.realms import LEARN_REALM, REALMS, WEBVPN_REALM


def test_realms_indexed_by_id():
    assert set(REALMS) == {"learn", "webvpn"}
    for key, realm in REALMS.items():
        assert realm.id == key


def test_realm_bootstrap_kinds():
    assert LEARN_REALM.bootstrap_kind == "direct"
    assert WEBVPN_REALM.bootstrap_kind == "oauth"


def test_realm_sso_app_ids_pin():
    assert LEARN_REALM.sso_app_id == "bb5df85216504820be7bba2b0ae1535b"
    assert WEBVPN_REALM.sso_app_id == "20843963f89b3072788f7fe75a5d9322"


def test_campus_apps_indexed_by_id():
    expected = {"info_portal", "transcript_bks", "transcript_yjs",
                "timetable_bks", "timetable_yjs"}
    assert set(CAMPUS_APPS) == expected


def test_info_portal_is_id_policy_no_parent():
    assert INFO_PORTAL.policy == "id"
    assert INFO_PORTAL.sso_app_id == "10000ea055dd8d81d09d5a1ba55d39ad"
    assert INFO_PORTAL.parent_app is None
    assert INFO_PORTAL.yyfwid == ""


@pytest.mark.parametrize("app,yyfwid", [
    (TRANSCRIPT_BKS, "B7EF0ADF9406335AD7905B30CD7B49B1"),
    (TRANSCRIPT_YJS, "E35232808C08C8C5F199F13BF6B7F5D0"),
    (TIMETABLE_BKS, "287C0C6D90ABB364CD5FDF1495199962"),
    (TIMETABLE_YJS, "BEABB32641DC4EC3510B048BAF42471A"),
])
def test_default_policy_app_pins(app, yyfwid):
    """pin specific yyfwid values copied from thu-info-lib — a future upstream
    change shows up clearly in the diff."""
    assert app.policy == "default"
    assert app.yyfwid == yyfwid
    assert app.parent_app is INFO_PORTAL
    assert app.sso_app_id == ""
