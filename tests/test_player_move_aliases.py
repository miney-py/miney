"""The four names that lead to ``move()``.

They exist so somebody looking for "teleport" finds something. What they must not do is
grow a second implementation next to ``move()`` - so every one of these tests asserts
that the call went through, and with which arguments.
"""
from __future__ import annotations

import math

import pytest

from miney.player import Player
from miney.point import Point


@pytest.fixture
def player() -> Player:
    p = Player.__new__(Player)
    p.name = "Steve"
    p.moves = []
    p.move = lambda **kwargs: p.moves.append(kwargs)
    return p


def test_teleport_is_move_with_a_destination(player):
    player.teleport(Point(10, 20, 30))
    assert player.moves == [{"destination": Point(10, 20, 30)}]


def test_look_at_is_move_with_a_look_at(player):
    player.look_at(Point(0, 20, 0))
    assert player.moves == [{"look_at": Point(0, 20, 0)}]


def test_fly_to_is_the_animated_move(player):
    player.fly_to(Point(50, 40, 50), duration=3)
    assert player.moves == [{"destination": Point(50, 40, 50), "smooth": True,
                             "duration": 3, "wait": False}]


def test_fly_to_can_wait(player):
    player.fly_to(Point(50, 40, 50), wait=True)
    assert player.moves[0]["wait"] is True
    assert player.moves[0]["smooth"] is True, "waiting needs something to wait for"


def test_turn_passes_both_angles(player):
    player.turn(yaw=math.pi, pitch=-math.pi / 8)
    assert player.moves == [{"yaw": math.pi, "pitch": -math.pi / 8}]


def test_turn_with_one_angle_leaves_the_other_alone(player):
    player.turn(yaw=0)
    assert player.moves == [{"yaw": 0, "pitch": None}]


def test_turn_with_no_angle_says_so_instead_of_doing_nothing(player):
    with pytest.raises(ValueError, match="look_at"):
        player.turn()
    assert player.moves == []
