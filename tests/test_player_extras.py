"""What a player is looking at, holding, pressing, and how hard they can be pushed.

All of these go the same way: one Lua chunk with the player bound to ``player``, and a
sentinel when there is no player to bind. The fake below answers by pattern, so a test
says what the server replied rather than what the Python did with it.

The two that are more than a passthrough get the most attention: :attr:`Player.keys`
throws away everything that is not a yes-or-no answer, because the same call carries
duplicates under old names and floats that do not exist on the oldest server Miney
supports; and :attr:`Player.looking_at` has to aim from the eyes rather than the feet.
"""
from __future__ import annotations

import pytest

from miney.exceptions import PlayerOffline
from miney.node import Node
from miney.player import Player
from miney.point import Point
from miney.vector import Vector


class _FakeLua:
    """Answers the chunks the player properties send, and records them all."""

    def __init__(self, online: bool = True, **answers) -> None:
        self.online = online
        self.answers = answers
        self.calls: list[str] = []

    def dumps(self, value):
        from miney.lua import Lua
        return Lua.dumps(self, value)

    def run(self, code, timeout=None, execution_id=None, wait=True):
        self.calls.append(code)
        if not self.online:
            return Player._OFFLINE

        body = code.split("end ", 1)[1] if "end " in code else code
        for marker, answer in self.answers.items():
            if marker in body:
                return answer() if callable(answer) else answer
        return True


class _FakeLuanti:
    def __init__(self, online: bool = True, **answers) -> None:
        self.lua = _FakeLua(online, **answers)


def _player(online: bool = True, **answers) -> Player:
    p = Player.__new__(Player)
    p.lt = _FakeLuanti(online, **answers)
    p.name = "Steve"
    return p


# --- looking_at --------------------------------------------------------------------

SEEN = {"x": 10, "y": 20, "z": 30, "name": "default:stone", "param1": 15, "param2": 0}


def test_looking_at_gives_back_a_node():
    p = _player(raycast=SEEN)
    target = p.looking_at

    assert isinstance(target, Node)
    assert (target.x, target.y, target.z) == (10, 20, 30)
    assert target.name == "default:stone"
    assert target.param1 == 15


def test_a_node_from_looking_at_is_a_point_too():
    """It has to go straight into anything that takes a position."""
    p = _player(raycast=SEEN)
    assert p.looking_at + Point(0, 1, 0) == Point(10, 21, 30)


def test_looking_at_the_sky_is_none():
    p = _player(raycast=None)
    assert p.looking_at is None


def test_the_ray_starts_at_the_eyes():
    """From get_pos() it would aim at the floor whenever the player looks level."""
    p = _player(raycast=SEEN)
    p.looking_at

    assert "eye_height" in p.lt.lua.calls[0]


def test_the_ray_sees_water_but_not_mobs():
    p = _player(raycast=SEEN)
    p.looking_at

    assert "minetest.raycast(eye, far, false, true)" in p.lt.lua.calls[0]


def test_the_reach_can_be_changed():
    p = _player(raycast=SEEN)
    p.look_range = 40
    p.looking_at

    assert "get_look_dir(), 40)" in p.lt.lua.calls[0]
    assert Player.look_range == 10, "one player's reach is not everybody's"


# --- wielding ----------------------------------------------------------------------

def test_wielding_is_the_item_name():
    p = _player(get_wielded_item="default:pick_mese")
    assert p.wielding == "default:pick_mese"


def test_an_empty_hand_is_an_empty_string():
    p = _player(get_wielded_item="")
    assert not p.wielding


def test_wielding_cannot_be_set():
    """Writing there replaces the whole stack, so there is no setter to trip over."""
    p = _player()
    with pytest.raises(AttributeError):
        p.wielding = "default:dirt"


# --- keys --------------------------------------------------------------------------

CONTROL = {
    "up": True, "down": False, "left": False, "right": False,
    "jump": True, "aux1": False, "sneak": False, "dig": True, "place": False,
    "zoom": False,
    "LMB": True, "RMB": False,          # the old names of dig and place
    "movement_x": 0.0, "movement_y": 1.0,   # floats, and not on a 5.9 server
}


def test_keys_says_what_is_held_down():
    p = _player(get_player_control=CONTROL)
    keys = p.keys

    assert keys["jump"] is True
    assert keys["sneak"] is False


def test_keys_drops_the_duplicates_and_the_floats():
    p = _player(get_player_control=CONTROL)
    keys = p.keys

    assert "LMB" not in keys and "RMB" not in keys
    assert "movement_x" not in keys
    assert all(isinstance(value, bool) for value in keys.values())


def test_keys_on_an_older_server_is_the_same_dictionary():
    """5.9 has no movement_x, and nothing about the answer may depend on that."""
    old = {name: value for name, value in CONTROL.items()
           if not name.startswith("movement_")}
    new = _player(get_player_control=CONTROL).keys
    assert _player(get_player_control=old).keys == new


# --- velocity and push -------------------------------------------------------------

def test_velocity_is_a_vector():
    p = _player(get_velocity={"x": 0.0, "y": -9.5, "z": 1.0})
    assert p.velocity == Vector(0.0, -9.5, 1.0)


def test_push_sends_the_force():
    p = _player()
    p.push(Vector(0, 20, 0))

    assert "add_velocity(" in p.lt.lua.calls[0]
    assert "y=20" in p.lt.lua.calls[0]


def test_push_refuses_a_point():
    """A Point is a place, a Vector is a shove. Guessing which was meant helps nobody."""
    p = _player()
    with pytest.raises(TypeError, match="Vector"):
        p.push(Point(0, 20, 0))


def test_push_refuses_a_plain_number():
    p = _player()
    with pytest.raises(TypeError, match="Vector"):
        p.push(20)


# --- size --------------------------------------------------------------------------

def test_size_reads_the_visual_size():
    p = _player(visual_size=2.5)
    assert p.size == 2.5


def test_size_sets_all_three_axes():
    p = _player()
    p.size = 3

    assert "visual_size={x = 3, y = 3, z = 3}" in p.lt.lua.calls[0].replace("visual_size = ", "visual_size=")


@pytest.mark.parametrize("bad", ["big", None, True])
def test_size_refuses_anything_that_is_not_a_number(bad):
    p = _player()
    with pytest.raises(TypeError, match="Size is a number"):
        p.size = bad


@pytest.mark.parametrize("bad", [0, -1])
def test_size_refuses_zero_and_below(bad):
    p = _player()
    with pytest.raises(ValueError, match="above 0"):
        p.size = bad


# --- respawn -----------------------------------------------------------------------

def test_respawn_asks_luanti_to_do_it():
    p = _player()
    p.respawn()

    assert "player:respawn()" in p.lt.lua.calls[0]


# --- armor_groups ------------------------------------------------------------------

def test_armor_groups_reads_the_table():
    p = _player(get_armor_groups={"fleshy": 100})
    assert p.armor_groups == {"fleshy": 100}


def test_armor_groups_of_a_game_that_set_none():
    p = _player(get_armor_groups=None)
    assert p.armor_groups == {}


def test_armor_groups_writes_the_whole_table():
    p = _player()
    p.armor_groups = {"fleshy": 50}

    assert "set_armor_groups({fleshy=50})" in p.lt.lua.calls[0]


@pytest.mark.parametrize("bad", [
    ["fleshy", 50],
    {"fleshy": "50"},
    {"fleshy": 1.5},
    {"fleshy": True},
    {7: 50},
])
def test_armor_groups_refuses_what_luanti_cannot_read(bad):
    p = _player()
    with pytest.raises(TypeError):
        p.armor_groups = bad


# --- offline -----------------------------------------------------------------------

@pytest.mark.parametrize("action", [
    lambda p: p.looking_at,
    lambda p: p.wielding,
    lambda p: p.keys,
    lambda p: p.velocity,
    lambda p: p.push(Vector(0, 1, 0)),
    lambda p: p.size,
    lambda p: setattr(p, "size", 2),
    lambda p: p.respawn(),
    lambda p: p.armor_groups,
    lambda p: setattr(p, "armor_groups", {"fleshy": 50}),
])
def test_an_offline_player_is_said_out_loud(action):
    p = _player(online=False)
    with pytest.raises(PlayerOffline, match="Steve"):
        action(p)
