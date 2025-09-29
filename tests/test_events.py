
import time
from datetime import datetime

import pytest
from miney.events import (
    create_event, ChatMessageEvent, PlayerJoinsEvent, PlayerLeavesEvent,
    ChatCommandEvent, GenericEvent
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
    minimal_raw_event["payload"] = {"name": "tester", "message": "hello"}

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
    minimal_raw_event["payload"] = {"name": "newbie", "last_login": None}

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
    minimal_raw_event["payload"] = {"name": "veteran", "last_login": ts}

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
    minimal_raw_event["payload"] = {"name": "leaver", "timed_out": True}

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
        "name": "mycmd",
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
