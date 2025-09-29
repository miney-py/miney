from dataclasses import dataclass, field, fields
import time
from typing import Any, Dict, Optional, Type
from datetime import datetime


@dataclass(frozen=True)
class Event:
    """Represents a generic event received from the server."""
    name: str  # The event name, e.g., "chat_message"
    client_id: str


@dataclass(frozen=True)
class ChatMessageEvent(Event):
    """An event representing a chat message."""
    name: str = field(init=False, default="chat_message")
    sender_name: str
    message: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class PlayerLeavesEvent(Event):
    """An event representing a player leaving the server."""
    name: str = field(init=False, default="player_leaves")
    player_name: str
    timed_out: bool
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class PlayerJoinsEvent(Event):
    """An event representing a player joining the server."""
    name: str = field(init=False, default="player_joins")
    player_name: str
    last_login: Optional[datetime]
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class ChatCommandEvent(Event):
    """An event representing a chat command invocation."""
    name: str = field(init=False, default="chatcommand")
    command_name: str
    issuer: str
    param: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class GenericEvent(Event):
    """An event for which no specific type is defined."""
    raw_payload: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)


# Mapping from event name string to the corresponding event class
_EVENT_CLASS_MAP: Dict[str, Type[Event]] = {
    "chat_message": ChatMessageEvent,
    "player_leaves": PlayerLeavesEvent,
    "player_joins": PlayerJoinsEvent,
    "chatcommand": ChatCommandEvent,
}


def create_event(raw_event: Dict[str, Any]) -> Event:
    """
    Factory function to create a specific Event object from a raw dictionary.
    This function flattens the 'payload' dictionary into the event's attributes.

    :param raw_event: The dictionary received from the server.
    :return: A specific subclass of Event (e.g., ChatMessageEvent).
    """
    event_name = raw_event.get("event", "unknown")
    raw_payload = raw_event.get("payload", {})

    event_class = _EVENT_CLASS_MAP.get(event_name)

    # Prepare arguments for the dataclass constructor
    common_args = {
        "client_id": raw_event.get("client_id", ""),
    }
    # Add timestamp only if it exists in the raw event, otherwise let factory handle it
    if "ts" in raw_event:
        common_args["timestamp"] = raw_event["ts"]

    event_args = raw_payload.copy()
    event_args.update(common_args)

    # Resolve ambiguous 'name' field from payload by renaming it
    if event_name == "chat_message":
        event_args["sender_name"] = event_args.pop("name", "")
    elif event_name in ("player_joins", "player_leaves"):
        event_args["player_name"] = event_args.pop("name", "")
    elif event_name == "chatcommand":
        event_args["command_name"] = event_args.pop("name", "")

    # Handle special data conversion for player_joins
    if event_name == "player_joins":
        last_login_ts = event_args.get("last_login")
        event_args["last_login"] = datetime.fromtimestamp(last_login_ts) if last_login_ts else None

    if event_class:
        # Filter args to only those expected by the constructor to avoid TypeError
        expected_fields = {f.name for f in fields(event_class) if f.init}
        filtered_args = {k: v for k, v in event_args.items() if k in expected_fields}
        return event_class(**filtered_args)
    else:
        # Fallback to a generic event for unknown event names
        return GenericEvent(name=event_name, raw_payload=raw_payload, **common_args)
