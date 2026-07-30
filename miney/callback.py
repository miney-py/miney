from typing import TYPE_CHECKING, Callable, List, Optional, Dict, Any, Tuple
from .events import EVENT_FIELDS, Event, create_event, ChatCommandEvent
from .point import Point
import json
import logging
import queue
import threading
import uuid
if TYPE_CHECKING:
    from .luanti import Luanti

logger = logging.getLogger(__name__)


def _is_comparable(value: Any) -> bool:
    """
    Whether a filter value is something an event field can be compared against.

    A filter is answered with ``==`` on the server, so a value has to be a single
    string, number or boolean, or a list of those. A position - the one table anybody
    would try - can never equal anything and would silently match nothing.

    :param value: What was written on the right-hand side of a filter field.
    :return: ``True`` if the server can compare it.
    """
    scalars = (str, int, float, bool)
    if isinstance(value, scalars):
        return True
    if isinstance(value, (list, tuple)):
        return bool(value) and all(isinstance(one, scalars) for one in value)
    return False


def _area_from(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Take the area out of a ``player_near`` registration and check it.

    ``pos`` and ``radius`` travel in the same dict as the filters, because one ``on()``
    for every event is the shape this library teaches. They are not filters though -
    a distance is not an ``==`` - so they are removed here, before the filter
    validation runs and rejects a ``Point`` it was never meant to see.

    :param parameters: The registration's parameters. The area keys are **removed**
        from it; what is left is an ordinary filter.
    :return: The area, ready for the wire.
    :raises ValueError: If the area is missing or does not describe a place.
    """
    if "pos" not in parameters:
        raise ValueError(
            "'player_near' has to be told where to watch. Put a place and a radius in "
            "the parameters: lt.callbacks.on('player_near', "
            "{'pos': Point(10, 20, 30), 'radius': 5})"
        )
    pos = parameters.pop("pos")
    if not isinstance(pos, Point):
        raise ValueError(
            f"'pos' has to be a Point, got {type(pos).__name__}: "
            f"{{'pos': Point(10, 20, 30), 'radius': 5}}"
        )

    if "radius" not in parameters:
        raise ValueError(
            "'player_near' has to be told how close is near, and there is no sensible "
            "default - too large and the handler fires for the whole map: "
            "{'pos': Point(10, 20, 30), 'radius': 5}"
        )
    radius = parameters.pop("radius")
    if isinstance(radius, bool) or not isinstance(radius, (int, float)) or radius < 1:
        raise ValueError(
            f"'radius' is how many blocks away still counts as near and has to be at "
            f"least 1, got {radius!r}."
        )

    interval = parameters.pop("interval", 0.25)
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) \
            or interval <= 0:
        raise ValueError(
            f"'interval' is how many seconds pass between two looks and has to be "
            f"greater than 0, got {interval!r}."
        )

    return {
        "pos": {"x": pos.x, "y": pos.y, "z": pos.z},
        "radius": float(radius),
        "interval": float(interval),
    }


class Callback:
    """
    Manages event and chat command registrations with the server.

    This class provides a way to handle server-side events using asynchronous
    callbacks. Use decorators like :meth:`~miney.callback.Callback.on` and
    :meth:`~miney.callback.Callback.command` to register functions that are
    automatically called when events occur. This is handled in a background thread.

    You can access this class via the :attr:`~miney.Luanti.callbacks` property.
    """
    #: Every event a handler can be registered for. The Lua mod knows the same names -
    #: see ``EVENTS`` in ``mod_data/miney/callbacks.lua`` - and what each one carries is
    #: the matching class in :mod:`miney.events`.
    SUPPORTED_EVENTS = {
        "chat_message", "player_leaves", "player_joins",
        "node_dug", "node_placed", "node_punched",
        "player_dies", "player_respawns", "player_punched", "player_hp_changed",
        "player_near",
    }

    def __init__(self, luanti: 'Luanti'):
        self.lt = luanti
        self._transport = luanti.transport
        self._client_id: str = str(uuid.uuid4())
        #: Handlers by event name, then by the id the server knows them under.
        self._event_handlers: Dict[str, Dict[str, Callable[[Event], None]]] = {}
        self._command_handlers: Dict[str, Callable[[Event], None]] = {}
        #: Each event as it arrived, together with the handler ids the mod addressed it
        #: to. Chat commands bring None; they are looked up by command name instead.
        self._events_queue: "queue.Queue[Tuple[Event, Optional[List[str]]]]" = queue.Queue()
        self._running = True
        self._dispatcher = threading.Thread(
            target=self._dispatch_loop, name="miney-callbacks-dispatcher", daemon=True
        )
        self._dispatcher.start()
        self._transport.add_listener(self._handle_record)
        logger.debug("Callback manager initialized with client_id=%s", self._client_id)

    def _send(self, payload: Dict[str, Any]) -> bool:
        """
        Send one registration or unregistration to the mod.

        :param payload: What the mod's callback half should do.
        :return: True if it went out.
        """
        if not self._transport.connected:
            logger.warning("Cannot send a callback registration: not connected.")
            return False
        return self._transport.send({"payload": json.dumps(payload, ensure_ascii=False)})


    def _dispatch_loop(self) -> None:
        """Deliver events to registered handlers asynchronously."""
        while self._running:
            try:
                event, handler_ids = self._events_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                # Use the Event object's attributes
                if event.name in self.SUPPORTED_EVENTS:
                    # The mod applied the filters and named who the event is for, so
                    # there is nothing left to decide here.
                    registered = self._event_handlers.get(event.name) or {}
                    for handler_id in handler_ids or ():
                        cb = registered.get(handler_id)
                        if cb is None:
                            logger.debug(
                                "Dropped a '%s' event for handler %s, which is gone.",
                                event.name, handler_id,
                            )
                            continue
                        try:
                            cb(event)
                        except Exception as e:
                            logger.error("Error in '%s' handler: %s", event.name, e, exc_info=True)
                elif isinstance(event, ChatCommandEvent):
                    # Access the command name directly from the event object
                    name = event.command_name
                    handler = self._command_handlers.get(name)
                    # Asked against None, not for truth: a callable object may well be
                    # falsy - an empty collector, a counter at zero - and `if handler`
                    # would drop its events in silence for as long as it stays empty,
                    # which is forever if it only fills up by being called.
                    if handler is not None:
                        try:
                            handler(event)
                        except Exception as e:
                            logger.error("Error in chatcommand handler '%s': %s", name, e, exc_info=True)
            finally:
                self._events_queue.task_done()

    def _handle_record(self, data: Dict[str, Any]) -> None:
        """
        Take one record off the transport and queue it if it is an event.

        Both halves of Miney listen on the same stream, so most of what arrives here
        belongs to :class:`~miney.lua.Lua` and is left alone.

        :param data: What the mod sent, already decoded.
        """
        # Ignore Lua execution results travelling on the same channel
        if "execution_id" in data or "result" in data:
            return

        if "error" in data:
            logger.error("Callback error from server: %s (code=%s)",
                         data.get("error"), data.get("code"))
            return

        if data.get("ok") is True:
            logger.debug("Callback ack received for action=%s client_id=%s",
                         data.get("action"), data.get("client_id"))
            return

        if "event" in data:
            # Create an Event object and put it in the queue
            event_obj = create_event(data)
            self._events_queue.put((event_obj, data.get("handlers")))
            logger.debug("Queued event %s for dispatch", event_obj.name)
            return

        logger.debug("Unhandled callbacks payload: %s", data)

    def on(self, event: str, parameters: Optional[Dict[str, Any]] = None) -> Callable:
        """
        Decorator to register a callback for an event.

        This is the recommended way to register event handlers. The decorated
        function will be called with a specific subclass of :class:`~miney.events.Event`
        when the corresponding event occurs on the server.

        .. code-block:: python

            from miney.events import PlayerJoinsEvent

            @lt.callbacks.on("player_joins")
            def on_player_join(event: PlayerJoinsEvent):
                print(f"Player {event.player_name} joined the game.")

        Pass ``parameters`` when you want some of the events and not all of them. It names
        fields of the event and the values worth waking up for; a list accepts any one of
        them. The comparison happens on the server, so everything it rejects never travels
        at all:

        .. code-block:: python

            @lt.callbacks.on("chat_message", {"sender_name": ["Steve", "Alex"]})
            def on_friend_speaks(event):
                print(f"{event.sender_name} said: {event.message}")

        The fields you may filter on are the attributes of the matching event class -
        :class:`~miney.events.ChatMessageEvent` has ``sender_name`` and ``message``.
        Anything else raises, rather than matching nothing in silence. Every event and
        what it carries is listed in :mod:`miney.events`.

        A filter value is compared with ``==`` on the server, so it has to be a string,
        a number, a boolean, or a list of those. A position cannot be filtered on -
        ``{"pos": Point(1, 2, 3)}`` raises. Ask for the whole event and decide in your
        own code:

        .. code-block:: python

            @lt.callbacks.on("node_dug")
            def deep_dig(event):
                if event.pos.y < 10:
                    lt.chat.send_to_all(f"{event.player_name} is digging deep.")

        One event is not a thing that happens to somebody but a place you are watching.
        ``player_near`` takes a ``pos`` and a ``radius`` in the same parameters dict,
        and fires when a player walks in:

        .. code-block:: python

            from miney import Point

            @lt.callbacks.on("player_near", {"pos": Point(10, 20, 30), "radius": 5})
            def treasure(event):
                lt.chat.send_to_player(event.player_name, "You found it!")

        It fires on **arriving**, once, not for every moment spent standing there.
        ``radius`` has no default on purpose - a wrong guess is a handler that goes off
        for the whole map. ``interval`` says how many seconds pass between two looks and
        is 0.25 unless you say otherwise. Ordinary filters work next to all of it:
        ``{"pos": ..., "radius": 5, "player_name": "Steve"}``.

        Every field named has to match, and the filter belongs to the one handler you are
        registering. Watching the same event twice for different things is fine, and each
        handler only ever sees what it asked for:

        .. code-block:: python

            @lt.callbacks.on("chat_message", {"sender_name": "Steve"})
            def steve_said_something(event):
                print("Steve:", event.message)

            @lt.callbacks.on("chat_message", {"message": "hello"})
            def someone_said_hello(event):
                lt.chat.send_to_all(f"Hello yourself, {event.sender_name}!")

        :param event: The name of the event to subscribe to.
        :param parameters: Event fields that have to match before the handler runs.
        :return: The decorator function.
        :raises ValueError: If the event does not exist, or `parameters` names a field
            the event does not carry.
        """
        def decorator(func: Callable[[Event], None]) -> Callable[[Event], None]:
            self.register(event, func, parameters)
            return func
        return decorator

    def command(
        self,
        name: str,
        params: str = "",
        description: str = "",
        privileges: Optional[Dict[str, bool]] = None,
    ) -> Callable:
        """
        Decorator to register a chat command.

        This is the recommended way to register chat commands.

        .. code-block:: python

            from miney.events import ChatCommandEvent

            @lt.callbacks.command("greet", "<name>", description="Greets a player.")
            def greet_command(event: ChatCommandEvent):
                lt.chat.send_to_all(f"Hello, {event.param}!")

        :param name: The name of the command.
        :param params: The command's parameter string (for /help).
        :param description: The command's description (for /help).
        :param privileges: Privileges required to execute the command.
        :return: The decorator function.
        """
        def decorator(func: Callable[[Event], None]) -> Callable[[Event], None]:
            self.register_command(name, func, params, description, privileges)
            return func
        return decorator

    def register(self, event: str, callback: Callable[[Event], None],
                 parameters: Optional[Dict[str, Any]] = None) -> str:
        """
        Register a callback for an event procedurally.

        This is an alternative to using the :meth:`~miney.callback.Callback.on`
        decorator. It returns a unique token for the registration.

        .. code-block:: python

            from miney.events import PlayerLeavesEvent

            def on_player_leave(event: PlayerLeavesEvent):
                print(f"Player {event.player_name} left.")

            lt.callbacks.register("player_leaves", on_player_leave)

        :param event: The name of the event to subscribe to.
        :param callback: The function to execute when the event occurs.
        :param parameters: Event fields that have to match before the handler runs, as
            described on :meth:`~miney.callback.Callback.on`.
        :return: A unique token for this registration.
        :raises ValueError: If the event does not exist, or `parameters` names a field
            the event does not carry.
        """
        if event not in self.SUPPORTED_EVENTS:
            raise ValueError(
                f"Event '{event}' is not supported. "
                f"Supported events are: {sorted(list(self.SUPPORTED_EVENTS))}"
            )
        if not callable(callback):
            raise ValueError("callback must be callable")

        # The area is not a filter and has to leave before the filter checks run. The
        # caller's dict is copied rather than emptied: they may well be reusing it for
        # a second area.
        area: Optional[Dict[str, Any]] = None
        if event == "player_near":
            parameters = dict(parameters) if parameters else {}
            area = _area_from(parameters)
            parameters = parameters or None

        # Checked here rather than only on the server: the mod answers asynchronously on
        # the same channel the events arrive on, so a rejection over there would reach
        # this process as a log line long after register() has returned. A misspelt field
        # has to raise where it was typed.
        if parameters:
            unknown = sorted(set(parameters) - EVENT_FIELDS[event])
            if unknown:
                raise ValueError(
                    f"Event '{event}' has no field '{unknown[0]}'. It sends: "
                    f"{', '.join(sorted(EVENT_FIELDS[event]))}."
                )
            for name, wanted in parameters.items():
                if not _is_comparable(wanted):
                    raise ValueError(
                        f"The filter for '{name}' has to be a string, a number, a "
                        f"boolean or a list of those - a filter is answered with '==' "
                        f"on the server. A position or any other structure cannot be "
                        f"compared that way; let the event through and decide in your "
                        f"own code, e.g. 'if event.pos.y < 10:'."
                    )

        # The token is the name this handler goes by on both sides. The mod stores the
        # filter under it and puts it on every event it sends, so an arriving event
        # already says which function it is for.
        token = str(uuid.uuid4())
        self._event_handlers.setdefault(event, {})[token] = callback

        payload: Dict[str, Any] = {
            "action": "register",
            "events": [event],
            "handler": token,
            "client_id": self._client_id,
        }
        if parameters:
            payload["filter"] = parameters
        if area:
            payload["area"] = area
        self._send(payload)
        logger.info("Registered a handler for '%s'%s", event,
                    " with a filter" if parameters else "")
        return token

    def unregister(self, event: str, token_or_callback: Any) -> None:
        """
        Deactivate an event subscription by token or callback function.

        It is generally easier to unregister by providing the original callback
        function reference.

        .. code-block:: python

            # Assuming 'on_player_leave' was registered before
            lt.callbacks.unregister("player_leaves", on_player_leave)

        :param event: The name of the event (e.g., "player_leaves").
        :param token_or_callback: The handler function or the token from `register()`.
        """
        handlers = self._event_handlers.get(event)
        if not handlers:
            if event not in self.SUPPORTED_EVENTS:
                logger.warning(
                    "Attempted to unregister a handler for an unsupported event: '%s'. "
                    "Supported events are: %s",
                    event,
                    sorted(list(self.SUPPORTED_EVENTS)),
                )
            return

        removed_key = None
        if isinstance(token_or_callback, str):
            removed_key = token_or_callback if token_or_callback in handlers else None
        else:
            for t, cb in list(handlers.items()):
                if cb is token_or_callback:
                    removed_key = t
                    break
        if not removed_key:
            return

        handlers.pop(removed_key, None)
        if not handlers:
            self._event_handlers.pop(event, None)

        # Named, so the other handlers for this event keep theirs. The mod drops the
        # subscription for the event once its last handler is gone.
        self._send({
            "action": "unregister",
            "events": [event],
            "handler": removed_key,
            "client_id": self._client_id,
        })
        logger.info("Unregistered a handler for '%s'", event)

    def register_command(self, name: str, callback: Callable[[Event], None],
                         params: str = "", description: str = "",
                         privileges: Optional[Dict[str, bool]] = None) -> str:
        """
        Register a chat command procedurally.

        This is an alternative to using the :meth:`~miney.callback.Callback.command`
        decorator.

        .. code-block:: python

            from miney.events import ChatCommandEvent

            def teleport_command(event: ChatCommandEvent):
                # Placeholder for teleport logic
                print(f"Teleporting {event.issuer} to {event.param}")

            lt.callbacks.register_command(
                "teleport",
                teleport_command,
                params="<x,y,z>",
                description="Teleport to coordinates."
            )

        :param name: The name of the command.
        :param callback: The function to call when the command is executed.
        :param params: The command's parameter string (for /help).
        :param description: The command's description (for /help).
        :param privileges: Privileges required to execute the command.
        :return: The command name.
        """
        if not name or not isinstance(name, str):
            raise ValueError("Command name must be a non-empty string")
        if not callable(callback):
            raise ValueError("callback must be callable")
        self._command_handlers[name] = callback

        definition = {
            "params": params or "",
            "description": description or f"Miney command '{name}'",
            "privs": privileges or {},
        }
        self._send({
            "action": "register_chatcommand",
            "name": name,
            "definition": definition,
            "client_id": self._client_id,
        })
        logger.info("Registered chat command '%s'", name)
        return name

    def unregister_command(self, name: str) -> None:
        """
        Unregister a previously registered chat command.

        .. code-block:: python

            lt.callbacks.unregister_command("teleport")

        :param name: The name of the command to unregister.
        """
        if not name or name not in self._command_handlers:
            return
        self._send({"action": "unregister_chatcommand", "name": name, "client_id": self._client_id})
        self._command_handlers.pop(name, None)
        logger.info("Unregistered chat command '%s'", name)

    def stop(self) -> None:
        """Stop dispatcher thread."""
        self._running = False

    def shutdown(self) -> None:
        """
        Best-effort cleanup: unregister all known subscriptions and commands, then stop dispatcher.
        """
        try:
            # Unregister commands first
            for name in list(self._command_handlers.keys()):
                self._send({"action": "unregister_chatcommand", "name": name, "client_id": self._client_id})
            self._command_handlers.clear()

            # Unregister event subscriptions. No handler named, so the mod drops every
            # one this connection left behind rather than them one at a time.
            for event in list(self._event_handlers.keys()):
                self._send({"action": "unregister", "events": [event], "client_id": self._client_id})
            self._event_handlers.clear()
        finally:
            self.stop()
            if self._dispatcher.is_alive():
                try:
                    self._dispatcher.join(timeout=1.0)
                except Exception:
                    pass
