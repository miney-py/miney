from __future__ import annotations
from miney.tool import ToolIterable
from miney.nodes import NameIterable


class _DummyToolParent:
    def __init__(self, cache):
        self._tools_cache = cache


class _DummyNamesParent:
    def __init__(self, cache):
        self._names_cache = cache


def test_tool_iterable_len():
    items = ["hammer", "wrench", "screwdriver"]
    parent = _DummyToolParent(items)
    it = ToolIterable(parent=parent, tool_types=items)
    assert len(it) == len(items)


def test_name_iterable_len():
    names = ["default:stone", "default:dirt"]
    parent = _DummyNamesParent(names)
    it = NameIterable(parent=parent, nodes_types=names)
    assert len(it) == len(names)
