"""Inputs that used to be ignored in silence now say what is wrong.

Every case here returned ``None``, ``[]`` or simply did nothing before, so a script
carried on believing it had placed its blocks.
"""
from __future__ import annotations
import pytest

import miney
from miney.inventory import Inventory
from miney.node import Node
from miney.nodes import Nodes
from miney.player import PlayerIterable
from miney.point import Point


class _FakeLua:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run(self, code, timeout=None, execution_id=None, wait=True):
        self.calls.append(code)
        return []

    def dumps(self, value):
        return repr(value)


class _FakeLuanti:
    def __init__(self) -> None:
        self.lua = _FakeLua()


@pytest.fixture
def nodes() -> Nodes:
    """A Nodes whose __init__ is skipped - it reads the node list off a server."""
    n = Nodes.__new__(Nodes)
    n.lt = _FakeLuanti()
    return n


@pytest.fixture
def players() -> PlayerIterable:
    p = PlayerIterable.__new__(PlayerIterable)
    p._PlayerIterable__online_players = ["Steve", "Ana"]
    p._PlayerIterable__mt = _FakeLuanti()
    return p


def _placed(nodes: Nodes) -> int:
    return nodes.lt.lua.calls[-1].count("minetest.set_node") if nodes.lt.lua.calls else 0


def test_set_accepts_any_collection(nodes):
    a = Node(1, 2, 3, name="default:stone")
    b = Node(4, 5, 6, name="default:stone")

    nodes.set(a)
    assert _placed(nodes) == 1

    nodes.set([a, b])
    assert _placed(nodes) == 2

    nodes.set((a, b))  # a tuple used to place nothing at all
    assert _placed(nodes) == 2

    nodes.set(n for n in (a, b))  # a generator is walked twice internally
    assert _placed(nodes) == 2


def test_set_accepts_a_node_subclass(nodes):
    class MyNode(Node):
        pass

    nodes.set(MyNode(1, 2, 3, name="default:stone"))
    assert _placed(nodes) == 1


def test_set_of_nothing_costs_no_round_trip(nodes):
    nodes.set([])
    assert nodes.lt.lua.calls == []


@pytest.mark.parametrize("bad", ["default:dirt", 42, None, {"name": "x"}])
def test_set_rejects_what_is_not_a_node(nodes, bad):
    with pytest.raises(TypeError, match=type(bad).__name__):
        nodes.set(bad)


def test_set_rejects_a_point_among_the_nodes(nodes):
    with pytest.raises(TypeError, match="Point"):
        nodes.set([Node(1, 2, 3), Point(4, 5, 6)])


def test_get_rejects_the_wrong_number_of_corners(nodes):
    with pytest.raises(ValueError, match="exactly two"):
        nodes.get([Point(0, 0, 0), Point(1, 1, 1), Point(2, 2, 2)])


@pytest.mark.parametrize("bad", ["somewhere", 42, None])
def test_get_rejects_what_is_not_a_point(nodes, bad):
    with pytest.raises(TypeError, match=type(bad).__name__):
        nodes.get(bad)


@pytest.mark.parametrize("call", ["add", "remove", "get_lists", "get_list"])
def test_inventory_without_a_player_or_node_raises(call):
    orphan = Inventory(_FakeLuanti(), parent="neither")
    args = ("default:dirt",) if call in ("add", "remove") else ()
    with pytest.raises(TypeError, match="only players and nodes"):
        getattr(orphan, call)(*args)


def test_unknown_player_names_who_is_online(players):
    with pytest.raises(miney.PlayerNotFoundError) as excinfo:
        players["Steev"]

    message = str(excinfo.value)
    assert "'Steev'" in message and "'Steve'" in message and "'Ana'" in message


def test_unknown_player_is_still_an_index_error(players):
    """Scripts written against the old IndexError have to keep working."""
    with pytest.raises(IndexError):
        players["Steev"]


def test_an_out_of_range_index_stays_a_plain_index_error(players):
    with pytest.raises(IndexError) as excinfo:
        players[99]

    assert not isinstance(excinfo.value, miney.PlayerNotFoundError)


def test_unknown_player_on_an_empty_server(players):
    players._PlayerIterable__online_players = []
    with pytest.raises(miney.PlayerNotFoundError, match="Nobody is online"):
        players["Steve"]
