"""``lt.nodes.light_at()`` - how bright it is at one place.

The number the mob spawners in most games look at. ``None`` where the map is not
loaded, which is a normal answer and not an error.
"""
from __future__ import annotations

import pytest

from miney.lua import Lua
from miney.nodes import Nodes
from miney.point import Point


class _FakeLua:
    def __init__(self, answer=None) -> None:
        self.calls: list[str] = []
        self.answer = answer
        self._real = Lua.__new__(Lua)

    def dumps(self, value):
        return self._real.dumps(value)

    def run(self, code, timeout=None, execution_id=None, wait=True):
        self.calls.append(code)
        return self.answer


class _FakeLuanti:
    def __init__(self, answer=None) -> None:
        self.lua = _FakeLua(answer)


@pytest.fixture
def nodes() -> Nodes:
    n = Nodes.__new__(Nodes)
    n.lt = _FakeLuanti()
    n._names_cache = ["air", "mcl_core:dirt", "mcl_core:stone"]
    return n


def test_light_at_asks_the_engine_and_loads_the_area(nodes):
    nodes.lt.lua.answer = 14

    assert nodes.light_at(Point(10, 20, 30)) == 14

    code = nodes.lt.lua.calls[0]
    assert "minetest.get_node_light" in code
    assert "load_area" in code


def test_light_at_answers_none_where_the_map_is_not_loaded(nodes):
    nodes.lt.lua.answer = None

    assert nodes.light_at(Point(10, 20, 30)) is None


def test_light_at_answers_zero_as_zero_and_not_as_none(nodes):
    nodes.lt.lua.answer = 0

    assert nodes.light_at(Point(10, 20, 30)) == 0


def test_light_at_refuses_something_that_is_not_a_point(nodes):
    with pytest.raises(TypeError, match="Point"):
        nodes.light_at((10, 20, 30))
