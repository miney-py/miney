"""Inventory builds its Lua from quoted values, and answers with a list either way."""
from __future__ import annotations
import pytest

from miney.inventory import Inventory
from miney.lua import Lua
from miney.node import Node
from miney.player import Player


class _RecordingLua:
    """Records the Lua it is given, and quotes with the real dumps()."""

    def __init__(self, answer=None) -> None:
        self.calls: list[str] = []
        self.answer = answer

    def run(self, code, timeout=None, execution_id=None, wait=True):
        self.calls.append(code)
        return self.answer

    def dumps(self, value):
        return Lua.dumps(self, value)


class _FakeLuanti:
    def __init__(self, answer=None) -> None:
        self.lua = _RecordingLua(answer)


def _player(name: str) -> Player:
    """A Player without its __init__, which reads the account off a server."""
    p = Player.__new__(Player)
    p.name = name
    return p


@pytest.fixture
def player_inventory() -> Inventory:
    return Inventory(_FakeLuanti(), _player("Steve"))


def test_add_and_remove_reach_the_right_inventory(player_inventory):
    lua = player_inventory.lt.lua

    player_inventory.add("mcl_core:apple", 5)
    assert 'name="Steve"' in lua.calls[-1]
    assert 'ItemStack("mcl_core:apple 5")' in lua.calls[-1]

    player_inventory.remove("mcl_core:apple", 5)
    assert "remove_item" in lua.calls[-1]


def test_a_node_inventory_is_found_by_position():
    inv = Inventory(_FakeLuanti(), Node(1, -2, 3, name="mcl_chests:chest"))
    inv.add("mcl_core:diamond")
    assert 'type="node"' in inv.lt.lua.calls[-1]
    assert "x=1" in inv.lt.lua.calls[-1] and "y=-2" in inv.lt.lua.calls[-1]


@pytest.mark.parametrize("hostile", [
    'evil") minetest.chat_send_all("PWNED',
    'quote " and \\ backslash',
    "newline\nand return\r",
])
def test_a_hostile_item_name_stays_one_string(player_inventory, hostile):
    """It used to go into the Lua source unquoted, so it could close the call."""
    player_inventory.add(hostile, 1)
    code = player_inventory.lt.lua.calls[-1]

    # Whatever it contained, the generated Lua is still a single add_item call.
    assert code.count("add_item") == 1
    assert "chat_send_all" not in code.replace(
        player_inventory.lt.lua.dumps(f"{hostile} 1"), ""
    )


def test_a_hostile_player_name_stays_one_string():
    inv = Inventory(_FakeLuanti(), _player('Bob") os.exit("'))
    inv.add("mcl_core:apple")
    assert "os.exit" not in inv.lt.lua.calls[-1].replace(
        inv.lt.lua.dumps('Bob") os.exit("'), ""
    )


def test_a_hostile_list_name_stays_one_string():
    inv = Inventory(_FakeLuanti([]), _player("Steve"))
    inv.get_list('main") or error("')
    assert inv.lt.lua.calls[-1].count("get_list") == 1


def test_an_empty_inventory_answers_with_a_list_not_none():
    """An empty Lua table arrives as None, and an empty chest is normal."""
    inv = Inventory(_FakeLuanti(answer=None), _player("Steve"))
    assert inv.get_list() == []
    assert inv.get_lists() == []
