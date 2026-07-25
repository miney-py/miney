
import time
from datetime import datetime

import pytest
from miney import Point
from miney.events import (
    create_event, ChatMessageEvent, PlayerJoinsEvent, PlayerLeavesEvent,
    ChatCommandEvent, GenericEvent, NodeDugEvent, NodePlacedEvent, NodePunchedEvent,
    PlayerDiesEvent, PlayerHpChangedEvent, PlayerPunchedEvent
)


@pytest.fixture
def minimal_raw_event():
    """Provides a minimal raw event dictionary."""
    return {
        "event": "some_event",
        "payload": {},
        "client_id": "test-client-123",
        "ts": time.time()
    }


def test_create_event_chat_message(minimal_raw_event):
    # Arrange
    minimal_raw_event["event"] = "chat_message"
    minimal_raw_event["payload"] = {"sender_name": "tester", "message": "hello"}

    # Act
    event = create_event(minimal_raw_event)

    # Assert
    assert isinstance(event, ChatMessageEvent)
    assert event.sender_name == "tester"
    assert event.message == "hello"
    assert event.client_id == "test-client-123"


def test_create_event_player_joins_new_player(minimal_raw_event):
    # Arrange
    minimal_raw_event["event"] = "player_joins"
    minimal_raw_event["payload"] = {"player_name": "newbie", "last_login": None}

    # Act
    event = create_event(minimal_raw_event)

    # Assert
    assert isinstance(event, PlayerJoinsEvent)
    assert event.player_name == "newbie"
    assert event.last_login is None


def test_create_event_player_joins_returning_player(minimal_raw_event):
    # Arrange
    ts = 1672531200  # 2023-01-01 00:00:00 UTC
    minimal_raw_event["event"] = "player_joins"
    minimal_raw_event["payload"] = {"player_name": "veteran", "last_login": ts}

    # Act
    event = create_event(minimal_raw_event)

    # Assert
    assert isinstance(event, PlayerJoinsEvent)
    assert event.player_name == "veteran"
    assert isinstance(event.last_login, datetime)
    assert event.last_login == datetime.fromtimestamp(ts)


def test_create_event_player_leaves(minimal_raw_event):
    # Arrange
    minimal_raw_event["event"] = "player_leaves"
    minimal_raw_event["payload"] = {"player_name": "leaver", "timed_out": True}

    # Act
    event = create_event(minimal_raw_event)

    # Assert
    assert isinstance(event, PlayerLeavesEvent)
    assert event.player_name == "leaver"
    assert event.timed_out is True


def test_create_event_chat_command(minimal_raw_event):
    # Arrange
    minimal_raw_event["event"] = "chatcommand"
    minimal_raw_event["payload"] = {
        "command_name": "mycmd",
        "issuer": "commander",
        "param": "some param"
    }

    # Act
    event = create_event(minimal_raw_event)

    # Assert
    assert isinstance(event, ChatCommandEvent)
    assert event.command_name == "mycmd"
    assert event.issuer == "commander"
    assert event.param == "some param"


def test_create_event_generic_for_unknown_event(minimal_raw_event):
    # Arrange
    minimal_raw_event["event"] = "some_new_unsupported_event"
    minimal_raw_event["payload"] = {"foo": "bar"}

    # Act
    event = create_event(minimal_raw_event)

    # Assert
    assert isinstance(event, GenericEvent)
    assert event.name == "some_new_unsupported_event"
    assert event.raw_payload == {"foo": "bar"}


def test_event_fields_lists_what_a_filter_may_match():
    from miney.events import EVENT_FIELDS

    assert EVENT_FIELDS["chat_message"] == {"sender_name", "message"}
    assert EVENT_FIELDS["player_joins"] == {"player_name", "last_login"}
    assert EVENT_FIELDS["player_leaves"] == {"player_name", "timed_out"}
    assert EVENT_FIELDS["node_dug"] == {"pos", "node_name", "player_name"}
    assert EVENT_FIELDS["player_hp_changed"] == {"player_name", "hp_change", "hp", "reason"}


@pytest.mark.parametrize("event_name, event_class", [
    ("node_dug", NodeDugEvent),
    ("node_placed", NodePlacedEvent),
    ("node_punched", NodePunchedEvent),
])
def test_a_node_event_arrives_with_a_point(minimal_raw_event, event_name, event_class):
    """The position travels as three numbers and has to arrive as something usable."""
    # Arrange
    minimal_raw_event["event"] = event_name
    minimal_raw_event["payload"] = {
        "pos": {"x": 10, "y": 20, "z": -30},
        "node_name": "mcl_core:dirt",
        "player_name": "tester",
    }

    # Act
    event = create_event(minimal_raw_event)

    # Assert
    assert isinstance(event, event_class)
    assert isinstance(event.pos, Point)
    assert (event.pos.x, event.pos.y, event.pos.z) == (10, 20, -30)
    assert event.node_name == "mcl_core:dirt"
    assert event.player_name == "tester"


def test_a_node_event_without_a_digger_carries_an_empty_name(minimal_raw_event):
    """Falling gravel and mods dig too, and neither has a player name."""
    # Arrange
    minimal_raw_event["event"] = "node_dug"
    minimal_raw_event["payload"] = {
        "pos": {"x": 0, "y": 0, "z": 0}, "node_name": "mcl_core:sand", "player_name": "",
    }

    # Act
    event = create_event(minimal_raw_event)

    # Assert
    assert event.player_name == ""


def test_create_event_player_dies(minimal_raw_event):
    # Arrange
    minimal_raw_event["event"] = "player_dies"
    minimal_raw_event["payload"] = {"player_name": "tester", "reason": "fall"}

    # Act
    event = create_event(minimal_raw_event)

    # Assert
    assert isinstance(event, PlayerDiesEvent)
    assert event.player_name == "tester"
    assert event.reason == "fall"


def test_create_event_player_hp_changed(minimal_raw_event):
    # Arrange
    minimal_raw_event["event"] = "player_hp_changed"
    minimal_raw_event["payload"] = {
        "player_name": "tester", "hp_change": -4, "hp": 16, "reason": "punch",
    }

    # Act
    event = create_event(minimal_raw_event)

    # Assert
    assert isinstance(event, PlayerHpChangedEvent)
    assert event.hp_change == -4
    assert event.hp == 16
    assert event.reason == "punch"


def test_create_event_player_punched(minimal_raw_event):
    # Arrange
    minimal_raw_event["event"] = "player_punched"
    minimal_raw_event["payload"] = {
        "player_name": "victim", "hitter_name": "", "damage": 2,
    }

    # Act
    event = create_event(minimal_raw_event)

    # Assert
    assert isinstance(event, PlayerPunchedEvent)
    assert event.hitter_name == "", "a mob has no name"
    assert event.damage == 2


def test_the_mod_and_python_agree_on_the_event_fields():
    """
    Both halves spell the payload fields, and a disagreement is invisible at runtime:
    the handler would simply be called with defaults and a filter would match nothing.
    """
    import re
    from pathlib import Path

    from miney.events import EVENT_FIELDS

    from miney.callback import Callback

    lua = (Path(__file__).parent.parent / "mod_data" / "miney" / "callbacks.lua").read_text(
        encoding="utf-8"
    )
    # The registrar is `on = minetest.register_on_something` for most events and a small
    # function for the one that needs an extra argument, so the match runs from the entry
    # name to its `keys`, whatever stands between them.
    entries = re.findall(
        r"(\w+) = \{\s*(?:--[^\n]*\n\s*)*on = .*?keys = \{([^}]*)\}", lua, re.S
    )
    assert entries, "No EVENTS entries found in callbacks.lua - did the table change shape?"

    names = {name for name, _ in entries}
    assert names == Callback.SUPPORTED_EVENTS, (
        "The mod and Miney disagree about which events exist: "
        f"only in the mod {sorted(names - Callback.SUPPORTED_EVENTS)}, "
        f"only in Python {sorted(Callback.SUPPORTED_EVENTS - names)}"
    )

    for name, keys in entries:
        in_lua = {key.strip().strip('"') for key in keys.split(",") if key.strip()}
        assert in_lua == set(EVENT_FIELDS[name]), f"'{name}' differs between the two halves"
