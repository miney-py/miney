"""``lt.nodes.grow_tree()`` - one call, one tree.

``core.spawn_tree`` wants a whole L-system definition, and the two fields that really
differ are the block names, which differ per *game*. The mod guesses those; ``height``
builds the axiom, and everything else is fixed.
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
    n.lt = _FakeLuanti(True)
    n._names_cache = ["air", "mcl_core:tree", "mcl_core:leaves", "mcl_core:dirt"]
    return n


def test_grow_tree_spawns_a_tree_and_loads_the_area(nodes):
    nodes.grow_tree(Point(0, 10, 0))

    code = nodes.lt.lua.calls[0]
    assert "minetest.spawn_tree" in code
    assert "load_area" in code


def test_grow_tree_lets_the_mod_guess_the_block_names(nodes):
    nodes.grow_tree(Point(0, 10, 0))

    code = nodes.lt.lua.calls[0]
    assert "default:tree" in code
    assert "mcl_core:tree" in code


def test_grow_tree_sends_the_names_it_was_given(nodes):
    nodes.grow_tree(Point(0, 10, 0), trunk="mcl_core:tree", leaves="mcl_core:leaves")

    code = nodes.lt.lua.calls[0]
    # Not just "the name appears somewhere" - the guesses table names it too. This is
    # the assignment the guessing then leaves alone.
    assert ('local trunk, leaves, fruit = "mcl_core:tree", "mcl_core:leaves", nil'
            in code)


def test_grow_tree_leaves_the_names_nil_when_it_should_guess(nodes):
    nodes.grow_tree(Point(0, 10, 0))

    assert "local trunk, leaves, fruit = nil, nil, nil" in nodes.lt.lua.calls[0]


def test_grow_tree_refuses_a_block_this_server_does_not_have(nodes):
    with pytest.raises(ValueError, match="no block called"):
        nodes.grow_tree(Point(0, 10, 0), trunk="nosuch:tree")


def test_grow_tree_default_height_reproduces_the_documented_apple_tree(nodes):
    nodes.grow_tree(Point(0, 10, 0))

    assert '"FFFFFAFFBF"' in nodes.lt.lua.calls[0]


def test_grow_tree_height_lengthens_the_trunk(nodes):
    nodes.grow_tree(Point(0, 10, 0), height=12)

    assert '"FFFFFFFFFAFFBF"' in nodes.lt.lua.calls[0]


def test_grow_tree_refuses_a_height_outside_the_range(nodes):
    with pytest.raises(ValueError, match="between 4 and 30"):
        nodes.grow_tree(Point(0, 10, 0), height=2)
    with pytest.raises(ValueError, match="between 4 and 30"):
        nodes.grow_tree(Point(0, 10, 0), height=99)


def test_grow_tree_refuses_something_that_is_not_a_point(nodes):
    with pytest.raises(TypeError, match="Point"):
        nodes.grow_tree((0, 10, 0))
