"""``lt.entities.near()`` - what is standing around a point.

Mobs, dropped items, anything a mod spawned. Players are in the engine's answer too
and are dropped unless asked for, because a player is always within any radius of
themselves.
"""
from __future__ import annotations

import pytest

from miney.entity import Entities, Entity
from miney.lua import Lua
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
def entities() -> Entities:
    return Entities(_FakeLuanti())


def test_near_builds_entities_from_what_the_server_answered(entities):
    entities.lt.lua.answer = [
        {"name": "mobs_mc:cow", "x": 12, "y": 8, "z": -3, "hp": 10, "is_player": False},
    ]

    found = entities.near(Point(10, 8, 0), radius=20)

    assert len(found) == 1
    assert found[0].name == "mobs_mc:cow"
    assert found[0].position == Point(12, 8, -3)
    assert found[0].hp == 10
    assert found[0].is_player is False


def test_near_asks_the_engine_with_the_radius_it_was_given(entities):
    entities.lt.lua.answer = []

    entities.near(Point(10, 8, 0), radius=20)

    code = entities.lt.lua.calls[0]
    assert "minetest.get_objects_inside_radius" in code
    assert "20" in code


def test_near_leaves_players_out_by_default(entities):
    entities.lt.lua.answer = []

    entities.near(Point(0, 0, 0))

    assert "local want_players = false" in entities.lt.lua.calls[0]


def test_near_asks_for_players_when_told_to(entities):
    entities.lt.lua.answer = []

    entities.near(Point(0, 0, 0), players=True)

    assert "local want_players = true" in entities.lt.lua.calls[0]


def test_near_answers_an_empty_list_when_nothing_is_there(entities):
    entities.lt.lua.answer = None

    assert entities.near(Point(0, 0, 0)) == []


def test_near_refuses_something_that_is_not_a_point(entities):
    with pytest.raises(TypeError, match="Point"):
        entities.near((0, 0, 0))


def test_near_refuses_a_radius_below_one(entities):
    with pytest.raises(ValueError, match="at least 1"):
        entities.near(Point(0, 0, 0), radius=0)


def test_entity_is_read_only():
    cow = Entity("mobs_mc:cow", Point(1, 2, 3), 10, False)

    with pytest.raises(AttributeError):
        cow.hp = 20


def test_entity_repr_names_the_thing_and_where_it_stands():
    cow = Entity("mobs_mc:cow", Point(12, 8, -3), 10, False)

    assert repr(cow) == '<Luanti Entity "mobs_mc:cow" at (12, 8, -3)>'
