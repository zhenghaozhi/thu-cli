"""``cli.output.to_json`` 单元测试（dataclass / Path / Enum 序列化）。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from thu_cli.cli.output import to_json


@dataclass
class _Sample:
    name: str
    count: int


def test_to_json_basic():
    s = _Sample(name="x", count=2)
    out = json.loads(to_json(s))
    assert out == {"name": "x", "count": 2}


def test_to_json_nested():
    out = json.loads(to_json({"a": [_Sample("y", 1), _Sample("z", 2)]}))
    assert out == {"a": [{"name": "y", "count": 1}, {"name": "z", "count": 2}]}


def test_to_json_path_becomes_str():
    out = json.loads(to_json({"p": Path("/tmp/x")}))
    assert out["p"] == "/tmp/x"


def test_to_json_enum_becomes_str():
    class K(Enum):
        A = "alpha"
    out = json.loads(to_json({"k": K.A}))
    assert out["k"] in ("K.A", "alpha")  # str(Enum) behaviour varies between versions


def test_to_json_dataclass_with_list_field():
    @dataclass
    class Holder:
        items: list

    out = json.loads(to_json(Holder(items=["a", "b", "c"])))
    assert out == {"items": ["a", "b", "c"]}
