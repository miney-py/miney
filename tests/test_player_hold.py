"""Holding a player, and giving them back.

``move()`` to a point above ground ends in a fall, so ``hold()`` has to switch gravity off
and damage with it, and ``release()`` has to put back what the player really had - not
Luanti's defaults over the top of it.

The fake below is a player as far as these two can tell: a physics table that *merges*,
an armor table that is *replaced*, and a metadata dict. Both of those habits are the
engine's (``l_object.cpp:1900`` and ``:385``), and getting either the wrong way round is
the bug these tests are here for.
"""
from __future__ import annotations

import re

import pytest

from miney.exceptions import PlayerOffline
from miney.player import Player


_SERIALIZE = re.compile(
    r"minetest\.serialize\(\{\s*gravity = player:get_physics_override\(\)\.gravity,"
    r"\s*armor_groups = player:get_armor_groups\(\)\s*\}\)",
    re.S,
)


class _FakePlayer:
    """The three pieces of Luanti state ``hold()`` and ``release()`` touch."""

    def __init__(self) -> None:
        self.physics = {"speed": 1.0, "jump": 1.0, "gravity": 1.0}
        self.armor_groups = {"fleshy": 100}
        self.meta: dict[str, str] = {}


class _FakeLua:
    """Runs the two chunks by pattern, against a :class:`_FakePlayer`."""

    KEY = "miney:before_hold"

    def __init__(self, online: bool = True) -> None:
        self.online = online
        self.player = _FakePlayer()
        self.calls: list[str] = []

    def dumps(self, value):
        if isinstance(value, str):
            return '"' + value + '"'
        return repr(value)

    def run(self, code, timeout=None, execution_id=None, wait=True):
        self.calls.append(code)

        if not self.online:
            return Player._OFFLINE

        if "get_meta():get_string" in code and "~= \"\"" in code:  # the `held` property
            return self.player.meta.get(self.KEY, "") != ""

        if "set_armor_groups({immortal = 1})" in code:
            self._hold(code)
            return True

        if "player:set_armor_groups(groups)" in code:
            self._release()
            return True

        raise AssertionError(f"unexpected Lua:\n{code}")

    def _hold(self, code: str) -> None:
        assert _SERIALIZE.search(code), "the record has to come from the live player"
        if not self.player.meta.get(self.KEY):
            # minetest.serialize round trips a table; a repr is as good for a test.
            self.player.meta[self.KEY] = repr({
                "gravity": self.player.physics["gravity"],
                "armor_groups": dict(self.player.armor_groups),
            })
        self.player.physics["gravity"] = 0            # set_physics_override merges
        self.player.armor_groups = {"immortal": 1}    # set_armor_groups replaces

    def _release(self) -> None:
        saved = self.player.meta.pop(self.KEY, "")
        before = eval(saved) if saved else {"gravity": 1, "armor_groups": {"fleshy": 100}}
        self.player.physics["gravity"] = before["gravity"]
        self.player.armor_groups = before["armor_groups"]


class _FakeLuanti:
    def __init__(self, online: bool = True) -> None:
        self.lua = _FakeLua(online)


def _player(online: bool = True) -> Player:
    p = Player.__new__(Player)
    p.lt = _FakeLuanti(online)
    p.name = "Steve"
    return p


def test_hold_switches_gravity_and_damage_off():
    p = _player()
    p.hold()

    assert p.lt.lua.player.physics["gravity"] == 0
    assert p.lt.lua.player.armor_groups == {"immortal": 1}


def test_hold_leaves_the_other_physics_alone():
    p = _player()
    p.lt.lua.player.physics["speed"] = 4.0
    p.hold()

    assert p.lt.lua.player.physics["speed"] == 4.0, "only gravity was asked for"


def test_hold_writes_the_way_back():
    p = _player()
    p.hold()

    assert "miney:before_hold" in p.lt.lua.player.meta


def test_a_second_hold_keeps_the_first_record():
    p = _player()
    p.lt.lua.player.physics["gravity"] = 0.5
    p.hold()
    p.hold()
    p.release()

    assert p.lt.lua.player.physics["gravity"] == 0.5, \
        "the second hold recorded the held state and lost the real one"


def test_release_puts_back_the_players_own_gravity():
    p = _player()
    p.lt.lua.player.physics["gravity"] = 0.5
    p.hold()
    p.release()

    assert p.lt.lua.player.physics["gravity"] == 0.5


def test_release_puts_back_the_whole_armor_table():
    p = _player()
    p.lt.lua.player.armor_groups = {"fleshy": 90, "snappy": 20}
    p.hold()
    p.release()

    assert p.lt.lua.player.armor_groups == {"fleshy": 90, "snappy": 20}


def test_release_without_a_hold_uses_luantis_defaults():
    p = _player()
    p.lt.lua.player.physics["gravity"] = 0
    p.lt.lua.player.armor_groups = {"immortal": 1}
    p.release()

    assert p.lt.lua.player.physics["gravity"] == 1
    assert p.lt.lua.player.armor_groups == {"fleshy": 100}


def test_release_twice_is_harmless():
    p = _player()
    p.hold()
    p.release()
    p.release()

    assert p.lt.lua.player.physics["gravity"] == 1


def test_held_says_what_is_going_on():
    p = _player()
    assert p.held is False
    p.hold()
    assert p.held is True
    p.release()
    assert p.held is False


def test_held_cannot_be_assigned():
    p = _player()
    with pytest.raises(AttributeError):
        p.held = True


@pytest.mark.parametrize("action", [
    lambda p: p.hold(),
    lambda p: p.release(),
    lambda p: p.held,
])
def test_an_offline_player_is_said_out_loud(action):
    p = _player(online=False)
    with pytest.raises(PlayerOffline, match="Steve"):
        action(p)
