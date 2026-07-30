"""``player_near`` - the one event Luanti has no registrar for.

The area travels in the same ``parameters`` dict every other event uses for filters,
and is pulled back out before the filter validation ever sees it. Everything below is
about that split and about the shape that reaches the wire.
"""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, Mock

import pytest

from miney import Point
from miney.callback import Callback
from miney.events import PlayerNearEvent, create_event

from conftest import FakeTransport


@pytest.fixture
def callback_env():
    transport = FakeTransport()
    mock_luanti = MagicMock()
    mock_luanti.transport = transport

    callback = Callback(mock_luanti)

    yield callback, transport

    callback.shutdown()


def _payload(transport, index=0):
    return json.loads(transport.sent[index]["payload"])


def test_the_area_leaves_the_parameters_dict_and_arrives_as_area(callback_env):
    callback, transport = callback_env

    callback.register("player_near", Mock(),
                      {"pos": Point(10, 20, 30), "radius": 5})

    sent = _payload(transport)
    assert sent["events"] == ["player_near"]
    assert sent["area"] == {"pos": {"x": 10, "y": 20, "z": 30},
                            "radius": 5.0, "interval": 0.25}
    assert "filter" not in sent


def test_an_ordinary_filter_survives_next_to_the_area(callback_env):
    callback, transport = callback_env

    callback.register("player_near", Mock(),
                      {"pos": Point(0, 5, 0), "radius": 3, "player_name": "Steve"})

    sent = _payload(transport)
    assert sent["filter"] == {"player_name": "Steve"}
    assert sent["area"]["radius"] == 3.0


def test_the_interval_can_be_given_and_defaults_to_a_quarter_second(callback_env):
    callback, transport = callback_env

    callback.register("player_near", Mock(),
                      {"pos": Point(0, 5, 0), "radius": 3, "interval": 1})

    assert _payload(transport)["area"]["interval"] == 1.0


def test_the_callers_dict_is_left_alone(callback_env):
    callback, _ = callback_env
    parameters = {"pos": Point(0, 5, 0), "radius": 3}

    callback.register("player_near", Mock(), parameters)

    assert parameters == {"pos": Point(0, 5, 0), "radius": 3}


@pytest.mark.parametrize("parameters, message", [
    ({"radius": 5}, "pos"),
    ({"pos": (1, 2, 3), "radius": 5}, "Point"),
    ({"pos": Point(0, 0, 0)}, "radius"),
    ({"pos": Point(0, 0, 0), "radius": 0}, "at least 1"),
    ({"pos": Point(0, 0, 0), "radius": 5, "interval": 0}, "greater than 0"),
])
def test_a_broken_area_raises_where_it_was_typed(callback_env, parameters, message):
    callback, _ = callback_env

    with pytest.raises(ValueError, match=message):
        callback.register("player_near", Mock(), parameters)


def test_nothing_is_sent_when_the_area_was_refused(callback_env):
    callback, transport = callback_env

    with pytest.raises(ValueError):
        callback.register("player_near", Mock(), {"radius": 5})

    assert transport.sent == []


def test_the_event_arrives_with_a_point_and_reaches_the_handler(callback_env):
    callback, transport = callback_env
    seen = []
    token = callback.register("player_near", seen.append,
                              {"pos": Point(10, 20, 30), "radius": 5})

    transport.deliver({
        "event": "player_near",
        "payload": {"player_name": "Steve",
                    "pos": {"x": 10, "y": 20, "z": 30},
                    "distance": 3.5},
        "ts": 1,
        "client_id": callback._client_id,
        "handlers": [token],
    })

    time.sleep(0.1)  # Give dispatcher time to process, as the other callback tests do

    assert len(seen) == 1
    assert isinstance(seen[0], PlayerNearEvent)
    assert seen[0].player_name == "Steve"
    assert seen[0].pos == Point(10, 20, 30)
    assert seen[0].distance == 3.5


def test_create_event_builds_a_player_near_event():
    event = create_event({
        "event": "player_near",
        "payload": {"player_name": "Steve",
                    "pos": {"x": 1, "y": 2, "z": 3},
                    "distance": 4.0},
        "client_id": "abc",
    })

    assert isinstance(event, PlayerNearEvent)
    assert event.pos == Point(1, 2, 3)
