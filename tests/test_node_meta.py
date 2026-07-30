"""``node.meta`` - the metadata Luanti keeps for one block.

A sign's text, a furnace's fuel, whatever the game wrote there. Unlike
``player.storage`` there is no prefix hiding anything: the keys the game wrote are
the whole point of the property.
"""
from __future__ import annotations

import pytest

from miney.lua import Lua
from miney.node import Node


class _FakeLua:
    """Records the Lua and answers with whatever the test put in ``answer``."""

    def __init__(self, answer=None) -> None:
        self.calls: list[str] = []
        self.answer = answer
        # The real quoting, so what the tests read is what the server would get.
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
def sign() -> Node:
    return Node(10, 20, 30, name="mcl_signs:standing_sign", luanti=_FakeLuanti())


def test_meta_reads_through_get_meta_at_the_nodes_position(sign):
    sign._luanti.lua.answer = {"text": "This way", "infotext": '"This way"'}

    assert dict(sign.meta) == {"text": "This way", "infotext": '"This way"'}

    code = sign._luanti.lua.calls[0]
    # dumps() writes a dict with identifier keys as {x=10, y=20, z=30}.
    assert "local p = {x=10, y=20, z=30}" in code
    assert "minetest.get_meta(p)" in code
    assert "to_table" in code


def test_meta_loads_the_mapblock_before_it_reads_or_writes(sign):
    # get_meta answers nil where the server does not hold the block, and a nil
    # MetaDataRef writes nowhere and reads back empty - the silent failure load_area
    # exists for.
    sign.meta["text"] = "This way"

    assert "minetest.load_area(p)" in sign._luanti.lua.calls[0]


def test_meta_writes_the_games_own_key_without_a_prefix(sign):
    sign.meta["text"] = "This way"

    code = sign._luanti.lua.calls[0]
    assert "set_string" in code
    assert '"text"' in code
    assert "miney:data:" not in code


def test_meta_is_the_same_object_every_time(sign):
    assert sign.meta is sign.meta


def test_meta_without_a_luanti_instance_says_so():
    with pytest.raises(AttributeError, match="not bound"):
        Node(1, 2, 3).meta
