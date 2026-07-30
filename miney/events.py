from dataclasses import dataclass, field, fields
import time
from typing import Any, Dict, Optional, Type
from datetime import datetime

from .point import Point


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
class NodeDugEvent(Event):
    """
    A block was dug away, sent once it is gone.

    .. code-block:: python

        @lt.callbacks.on("node_dug")
        def cave_in(event):
            print(f"{event.player_name} dug {event.node_name} at {event.pos}")

    A block removed by a mod, by falling gravel or by an explosion has no digger, and
    ``player_name`` is then an empty string.

    Blocks a script removes do not send this event: neither :meth:`~miney.Nodes.fill`
    nor :meth:`~miney.Nodes.set` digs anything, they write the map directly. This is
    about what the people in the world do.
    """
    name: str = field(init=False, default="node_dug")
    #: Where the block was, as a :class:`~miney.Point`.
    pos: Point
    #: What was dug, e.g. ``"mcl_core:dirt"``.
    node_name: str
    #: Who dug it, or ``""`` if nobody did.
    player_name: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class NodePlacedEvent(Event):
    """
    A block was placed, sent once it is there.

    .. code-block:: python

        @lt.callbacks.on("node_placed", {"node_name": "mcl_core:dirt"})
        def no_dirt_towers(event):
            lt.chat.send_to_all(f"{event.player_name} placed dirt at {event.pos}")

    Sent when somebody *places* a block. Blocks written by a script are not placed but
    set - :meth:`~miney.Nodes.set` and :meth:`~miney.Nodes.fill` send nothing - so a
    handler that builds something cannot set itself off.
    """
    name: str = field(init=False, default="node_placed")
    #: Where it went, as a :class:`~miney.Point`.
    pos: Point
    #: What was placed.
    node_name: str
    #: Who placed it, or ``""`` for a block a mod placed.
    player_name: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class NodePunchedEvent(Event):
    """
    A block was hit without being dug - one left click, not a finished dig.

    .. code-block:: python

        @lt.callbacks.on("node_punched")
        def knock_knock(event):
            lt.chat.send_to_player(event.player_name, f"That is a {event.node_name}.")

    Hitting a block a player *can* dig sends this first and
    :class:`~miney.events.NodeDugEvent` a moment later. A block nobody can dig - bedrock -
    only ever sends this one.
    """
    name: str = field(init=False, default="node_punched")
    #: Which block was hit, as a :class:`~miney.Point`.
    pos: Point
    #: What was hit.
    node_name: str
    #: Who hit it, or ``""``.
    player_name: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class PlayerDiesEvent(Event):
    """
    A player died.

    .. code-block:: python

        @lt.callbacks.on("player_dies")
        def condolences(event):
            lt.chat.send_to_all(f"{event.player_name} died of {event.reason}.")

    The player is dead when this arrives and stays where they died until they respawn -
    :class:`~miney.events.PlayerRespawnsEvent` is where a script sends them somewhere.
    """
    name: str = field(init=False, default="player_dies")
    #: Who died.
    player_name: str
    #: What killed them, as Luanti names it: ``"punch"``, ``"fall"``, ``"node_damage"``,
    #: ``"drown"``, ``"set_hp"``, or ``"unknown"``.
    reason: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class PlayerRespawnsEvent(Event):
    """
    A player is coming back, sent before the game decides where to put them.

    .. code-block:: python

        from miney import Point

        @lt.callbacks.on("player_respawns")
        def home_again(event):
            lt.players[event.player_name].move(destination=Point(0, 20, 0))

    The move has to wait for this event rather than for
    :class:`~miney.events.PlayerDiesEvent`: the game repositions the player after this
    callback, so anything a script does at death time is overwritten a moment later.
    """
    name: str = field(init=False, default="player_respawns")
    #: Who is respawning.
    player_name: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class PlayerPunchedEvent(Event):
    """
    A player was hit by someone or something.

    .. code-block:: python

        @lt.callbacks.on("player_punched")
        def bodyguard(event):
            if event.hitter_name:
                lt.chat.send_to_all(f"{event.hitter_name} hit {event.player_name}!")

    Sent for the notification only - the hit lands either way, and the damage is what
    the engine calculated before any armour the game applies afterwards. A mob or an
    arrow leaves ``hitter_name`` empty, because only players have names.
    """
    name: str = field(init=False, default="player_punched")
    #: Who was hit.
    player_name: str
    #: Who hit them, or ``""`` when it was not a player.
    hitter_name: str
    #: The damage the engine calculated, in half hearts.
    damage: float
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class PlayerHpChangedEvent(Event):
    """
    A player lost or gained health.

    .. code-block:: python

        @lt.callbacks.on("player_hp_changed")
        def nurse(event):
            if event.hp < 6:
                lt.chat.send_to_player(event.player_name, "Careful - you are nearly dead.")

    Damage sends a negative ``hp_change``, healing a positive one. Setting
    :attr:`player.hp <miney.Player.hp>` from a script sends one too, with ``reason``
    ``"set_hp"``. A player who is already dead takes no more damage and sends nothing;
    healing someone who is already full does send an event.
    """
    name: str = field(init=False, default="player_hp_changed")
    #: Whose health changed.
    player_name: str
    #: How much, negative for damage.
    hp_change: float
    #: What they have left afterwards, out of 20 in most games.
    hp: float
    #: Why, as Luanti names it: ``"punch"``, ``"fall"``, ``"node_damage"``, ``"drown"``,
    #: ``"set_hp"``, or ``"unknown"``.
    reason: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class PlayerNearEvent(Event):
    """
    A player walked into a place you are watching.

    .. code-block:: python

        from miney import Point

        @lt.callbacks.on("player_near", {"pos": Point(10, 20, 30), "radius": 5})
        def welcome(event):
            lt.chat.send_to_player(event.player_name, "You found it!")

    The one event Luanti has no register function for, so Miney's mod produces it: it
    measures the distance from every player to every place you asked about, four times
    a second by default.

    It fires when somebody **arrives**, once, not for every moment they spend standing
    there. Walking out and coming back fires it again.

    ``pos`` is the place *you* named, not where the player is - one handler can watch
    several places, and it has to be able to tell which one went off.
    """
    name: str = field(init=False, default="player_near")
    #: Who arrived.
    player_name: str
    #: The place being watched, as a :class:`~miney.Point`.
    pos: Point
    #: How far from that place they were when it was noticed, in blocks.
    distance: float
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
    "node_dug": NodeDugEvent,
    "node_placed": NodePlacedEvent,
    "node_punched": NodePunchedEvent,
    "player_dies": PlayerDiesEvent,
    "player_respawns": PlayerRespawnsEvent,
    "player_punched": PlayerPunchedEvent,
    "player_hp_changed": PlayerHpChangedEvent,
    "player_near": PlayerNearEvent,
}

#: What each event carries, and therefore what a subscription filter may match on.
#:
#: Read off the dataclasses rather than written out again, so it cannot drift away from
#: what a handler actually receives. ``client_id`` and ``timestamp`` are dropped because
#: they belong to the envelope around the event, not to the thing that happened.
EVENT_FIELDS: Dict[str, frozenset] = {
    name: frozenset(
        f.name for f in fields(cls)
        if f.init and f.name not in ("client_id", "timestamp")
    )
    for name, cls in _EVENT_CLASS_MAP.items()
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

    # The mod names the payload fields exactly like the attributes below, so the payload
    # goes into the constructor as it arrives. It used to send 'name' for the sender, the
    # player and the command alike, and every one of those needed its own renaming branch
    # here - see MOD_API 3 in mod_data/miney/init.lua.
    event_args = raw_payload.copy()
    event_args.update(common_args)

    # Handle special data conversion for player_joins
    if event_name == "player_joins":
        last_login_ts = event_args.get("last_login")
        event_args["last_login"] = datetime.fromtimestamp(last_login_ts) if last_login_ts else None

    # A position travels as three numbers and arrives as a Point, so an event can be
    # handed straight to nodes.get(), nodes.set() or player.move() without unpacking it.
    position = event_args.get("pos")
    if isinstance(position, dict):
        event_args["pos"] = Point(position.get("x", 0), position.get("y", 0),
                                  position.get("z", 0))

    if event_class:
        # Filter args to only those expected by the constructor to avoid TypeError
        expected_fields = {f.name for f in fields(event_class) if f.init}
        filtered_args = {k: v for k, v in event_args.items() if k in expected_fields}
        return event_class(**filtered_args)
    else:
        # Fallback to a generic event for unknown event names
        return GenericEvent(name=event_name, raw_payload=raw_payload, **common_args)
