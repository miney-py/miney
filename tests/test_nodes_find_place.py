"""Reading the world, and writing it the way a player does.

``set()`` writes a block and skips everything that makes it work, so ``place()`` and
``dig()`` have to go through ``minetest.place_node`` / ``dig_node`` instead - and both
of those quietly do nothing where the map is not loaded, which is what ``load_area``
in front of them is for.

``find()`` and ``find_in()`` are the other half: the answer comes back as a position
plus the name that is really standing there, because ``"group:tree"`` matches several.
"""
from __future__ import annotations

import pytest

from miney.lua import Lua
from miney.node import Node
from miney.nodes import Nodes
from miney.point import Point


class _FakeLua:
    """Records the Lua and answers with whatever the test put in ``answer``."""

    def __init__(self, answer=None) -> None:
        self.calls: list[str] = []
        self.answer = answer
        # The real quoting, so what the tests read is what the server would get.
        # dumps() touches nothing on the instance, so it needs no transport.
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
    n._names_cache = ["air", "mcl_core:dirt", "mcl_core:stone", "mcl_chests:chest"]
    return n


# --- place ------------------------------------------------------------------------

def test_place_goes_through_place_node_and_loads_the_area(nodes):
    nodes.lt.lua.answer = 1
    placed = nodes.place(Node(10, 20, 30, name="mcl_chests:chest"))

    code = nodes.lt.lua.calls[0]
    assert placed == 1
    assert "minetest.place_node" in code
    assert "minetest.set_node" not in code, "that is set(), and it is the bug"
    assert "minetest.load_area" in code, "place_node does nothing in unloaded map"
    assert code.rstrip().endswith("return placed")


def test_place_without_a_player_places_for_nobody(nodes):
    nodes.lt.lua.answer = 1
    nodes.place(Node(1, 2, 3, name="mcl_core:stone"))

    code = nodes.lt.lua.calls[0]
    assert "nil)" in code
    assert "get_player_by_name" not in code


def test_place_with_a_player_looks_them_up_first_and_stops_if_they_are_gone(nodes):
    nodes.lt.lua.answer = 1
    nodes.place(Node(1, 2, 3, name="mcl_core:stone"), player="Steve")

    code = nodes.lt.lua.calls[0]
    assert 'get_player_by_name("Steve")' in code
    assert code.index("get_player_by_name") < code.index("place_node")
    assert "error(" in code, "a player who is not there must not become 'nobody'"
    assert ", who)" in code


def test_place_takes_a_player_object_by_name(nodes):
    class _Player:
        name = "Steve"

    nodes.lt.lua.answer = 1
    nodes.place(Node(1, 2, 3, name="mcl_core:stone"), player=_Player())
    assert 'get_player_by_name("Steve")' in nodes.lt.lua.calls[0]


def test_place_counts_what_the_server_really_placed(nodes):
    nodes.lt.lua.answer = 2  # the third was protected
    placed = nodes.place([Node(1, 2, 3, name="mcl_core:stone"),
                          Node(1, 3, 3, name="mcl_core:stone"),
                          Node(1, 4, 3, name="mcl_core:stone")])
    assert placed == 2


def test_placing_nothing_costs_no_round_trip(nodes):
    assert nodes.place([]) == 0
    assert nodes.lt.lua.calls == []


def test_place_refuses_a_bare_name(nodes):
    with pytest.raises(TypeError, match="needs a position"):
        nodes.place("mcl_core:stone")


def test_place_refuses_a_point_without_a_name(nodes):
    with pytest.raises(TypeError, match="carries no node name"):
        nodes.place([Point(1, 2, 3)])


def test_place_refuses_something_that_is_not_a_player(nodes):
    with pytest.raises(TypeError, match="player name or a Player"):
        nodes.place(Node(1, 2, 3, name="mcl_core:stone"), player=42)


# --- dig --------------------------------------------------------------------------

def test_dig_goes_through_dig_node_and_counts(nodes):
    nodes.lt.lua.answer = 3
    dug = nodes.dig([Point(10, 20, 30), Point(10, 21, 30), Point(10, 22, 30)])

    code = nodes.lt.lua.calls[0]
    assert dug == 3
    assert code.count("minetest.dig_node") == 3
    assert "minetest.load_area" in code


def test_dig_takes_a_single_node_too(nodes):
    nodes.lt.lua.answer = 1
    assert nodes.dig(Node(1, 2, 3, name="mcl_core:stone")) == 1
    assert nodes.lt.lua.calls[0].count("minetest.dig_node") == 1


def test_dig_gives_the_drops_to_the_player_who_digs(nodes):
    nodes.lt.lua.answer = 1
    nodes.dig(Point(1, 2, 3), player="Steve")
    assert ", who)" in nodes.lt.lua.calls[0]


def test_dig_rounds_a_fractional_position_down(nodes):
    nodes.lt.lua.answer = 1
    nodes.dig(Point(1.7, 2.9, -0.5))
    assert "x=1, y=2, z=-1" in nodes.lt.lua.calls[0]


def test_digging_nothing_costs_no_round_trip(nodes):
    assert nodes.dig([]) == 0
    assert nodes.lt.lua.calls == []


def test_dig_refuses_something_that_is_not_a_point(nodes):
    with pytest.raises(TypeError, match="must be a Point"):
        nodes.dig("10, 20, 30")


# --- find -------------------------------------------------------------------------

def test_find_returns_a_node_with_the_name_that_is_really_there(nodes):
    nodes.lt.lua.answer = {"x": 4, "y": 5, "z": 6, "name": "mcl_core:tree"}
    found = nodes.find("group:tree", near=Point(0, 0, 0), radius=20)

    assert isinstance(found, Node)
    assert (found.x, found.y, found.z) == (4, 5, 6)
    assert found.name == "mcl_core:tree"
    assert found._luanti is nodes.lt, "so node.inventory works on what was found"


def test_find_searches_the_point_itself_as_well(nodes):
    nodes.lt.lua.answer = None
    nodes.find("mcl_core:dirt", near=Point(0, 0, 0))

    code = nodes.lt.lua.calls[0]
    assert "find_node_near" in code
    assert ", true)" in code, "standing on it and not finding it reads as a bug"
    assert "minetest.load_area" in code


def test_find_answers_none_when_there_is_nothing(nodes):
    nodes.lt.lua.answer = None
    assert nodes.find("mcl_core:dirt", near=Point(0, 0, 0)) is None


def test_find_takes_several_names(nodes):
    nodes.lt.lua.answer = None
    nodes.find(["mcl_core:dirt", "mcl_core:stone"], near=Point(0, 0, 0))
    assert '{"mcl_core:dirt", "mcl_core:stone"}' in nodes.lt.lua.calls[0]


def test_find_refuses_a_name_this_server_does_not_have(nodes):
    with pytest.raises(ValueError, match="no block called"):
        nodes.find("mcl_core:cheese", near=Point(0, 0, 0))


def test_find_lets_a_group_through_unchecked(nodes):
    nodes.lt.lua.answer = None
    nodes.find("group:water", near=Point(0, 0, 0))  # no such entry in _names_cache
    assert '"group:water"' in nodes.lt.lua.calls[0]


def test_find_refuses_a_place_that_is_not_a_point(nodes):
    with pytest.raises(TypeError, match="'near' must be a Point"):
        nodes.find("mcl_core:dirt", near=(0, 0, 0))


@pytest.mark.parametrize("radius", [0, -3, "ten", True])
def test_find_refuses_a_radius_that_cannot_search(nodes, radius):
    with pytest.raises(ValueError, match="at least 1"):
        nodes.find("mcl_core:dirt", near=Point(0, 0, 0), radius=radius)


# --- find_in ----------------------------------------------------------------------

def test_find_in_returns_every_match_as_a_node(nodes):
    nodes.lt.lua.answer = [{"x": 1, "y": 2, "z": 3, "name": "mcl_core:dirt"},
                           {"x": 4, "y": 5, "z": 6, "name": "mcl_core:dirt"}]
    found = nodes.find_in(Point(0, 0, 0), Point(10, 10, 10), "mcl_core:dirt")

    assert [(n.x, n.y, n.z) for n in found] == [(1, 2, 3), (4, 5, 6)]
    assert all(isinstance(n, Node) for n in found)


def test_find_in_asks_for_the_surface_when_told_to(nodes):
    nodes.lt.lua.answer = []
    nodes.find_in(Point(0, 0, 0), Point(10, 10, 10), "mcl_core:stone", under_air=True)
    assert "find_nodes_in_area_under_air" in nodes.lt.lua.calls[0]


def test_find_in_asks_for_the_whole_box_by_default(nodes):
    nodes.lt.lua.answer = []
    nodes.find_in(Point(0, 0, 0), Point(10, 10, 10), "mcl_core:stone")

    code = nodes.lt.lua.calls[0]
    assert "find_nodes_in_area(" in code
    assert "under_air" not in code
    assert "minetest.load_area" in code


def test_find_in_survives_an_empty_answer(nodes):
    # An empty Lua table comes back through write_json as {}, not [].
    nodes.lt.lua.answer = {}
    assert nodes.find_in(Point(0, 0, 0), Point(1, 1, 1), "mcl_core:dirt") == []


def test_find_in_refuses_corners_that_are_not_points(nodes):
    with pytest.raises(TypeError, match="'end' must be a Point"):
        nodes.find_in(Point(0, 0, 0), (1, 1, 1), "mcl_core:dirt")
