"""Waiting for a smooth move to finish.

The server frame, not the duration, decides when an animation is over, so waiting is a
question asked repeatedly rather than a sleep of the right length. These check that the
question is asked, that it stops being asked, and that it is refused where there is
nothing to wait for.
"""
from __future__ import annotations
import pytest

from miney.player import Player
from miney.point import Point


class _FakeLua:
    """Answers ``miney_task_busy`` a fixed number of times with True."""

    def __init__(self, busy_answers: int = 0) -> None:
        self.busy_left = busy_answers
        self.calls: list[str] = []

    def run(self, code, timeout=None, execution_id=None, wait=True):
        self.calls.append(code)
        if "miney_task_busy" in code:
            if self.busy_left > 0:
                self.busy_left -= 1
                return True
            return False
        return None

    def dumps(self, value):
        if isinstance(value, str):
            return '"' + value + '"'
        return repr(value)


class _FakeLuanti:
    def __init__(self, busy_answers: int = 0) -> None:
        self.lua = _FakeLua(busy_answers)


def _player(busy_answers: int = 0) -> Player:
    p = Player.__new__(Player)
    p.lt = _FakeLuanti(busy_answers)
    p.name = "Steve"
    return p


@pytest.fixture(autouse=True)
def no_real_sleeping(monkeypatch):
    monkeypatch.setattr("miney.player.time.sleep", lambda seconds: None)


def test_wait_without_smooth_is_refused():
    with pytest.raises(ValueError, match="smooth=True"):
        _player().move(destination=Point(1, 2, 3), wait=True)


def test_a_smooth_move_without_wait_asks_nothing():
    p = _player()
    p.move(destination=Point(1, 2, 3), smooth=True, duration=2)

    assert not any("miney_task_busy" in c for c in p.lt.lua.calls)


def test_wait_asks_until_the_answer_is_no():
    p = _player(busy_answers=3)
    p.move(destination=Point(1, 2, 3), smooth=True, duration=2, wait=True)

    asked = [c for c in p.lt.lua.calls if "miney_task_busy" in c]
    assert len(asked) == 4, "three times busy, then once more to hear it is done"


def test_the_key_names_this_player():
    p = _player(busy_answers=1)
    p.move(destination=Point(1, 2, 3), smooth=True, wait=True)

    asked = [c for c in p.lt.lua.calls if "miney_task_busy" in c][0]
    assert '"move:Steve"' in asked


def test_the_animation_is_started_before_it_is_waited_for():
    p = _player(busy_answers=1)
    p.move(destination=Point(1, 2, 3), smooth=True, wait=True)

    order = [("smooth_move" in c, "miney_task_busy" in c) for c in p.lt.lua.calls]
    assert order[0] == (True, False)


def test_an_instant_move_still_needs_no_animation():
    p = _player()
    p.move(destination=Point(1, 2, 3))

    assert not any("smooth_move" in c for c in p.lt.lua.calls)
