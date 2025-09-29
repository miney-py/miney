from typing import TYPE_CHECKING, Callable, Optional, Dict, Any
from .events import Event, create_event, ChatCommandEvent
import json
import logging
import queue
import threading
import time
import uuid
if TYPE_CHECKING:
    from .luanti import Luanti

logger = logging.getLogger(__name__)

class Callback:
    """
    Manages event and chat command registrations with the server.

    This class provides a way to handle server-side events using asynchronous
    callbacks. Use decorators like :meth:`~miney.callback.Callback.on` and
    :meth:`~miney.callback.Callback.command` to register functions that are
    automatically called when events occur. This is handled in a background thread.

    You can access this class via the :attr:`~miney.luanti.Luanti.callbacks` property.
    """
    SUPPORTED_EVENTS = {"chat_message", "player_leaves", "player_joins"}

    def __init__(self, luanti: 'Luanti'):
        self.lt = luanti
        self._client = luanti.luanti
        self._client_id: str = str(uuid.uuid4())
        self._event_handlers: Dict[str, Dict[str, Callable[[Event], None]]] = {}
        self._command_handlers: Dict[str, Callable[[Event], None]] = {}
        self._events_queue: "queue.Queue[Event]" = queue.Queue()
        self._running = True
        self._dispatcher = threading.Thread(
            target=self._dispatch_loop, name="miney-callbacks-dispatcher", daemon=True
        )
        self._dispatcher.start()
        self._code_form_shown: bool = False
        self._code_form_warmup_sent: bool = False
        if self._client and self._client.command_handler:
            self._client.command_handler.register_formspec_handler(
                "miney:code_form", self._handle_miney_callbacks
            )
        if self._client and self._client.state.authenticated:
            self._ensure_code_form_open()
        logger.debug("Callback manager initialized with client_id=%s", self._client_id)

    def _send(self, payload: Dict[str, Any]) -> bool:
        """Send a JSON payload via the 'miney:code_form' channel."""
        if not self._client or not self._client.state.authenticated:
            logger.warning("Cannot send callback registration: client not authenticated.")
            return False
        # Ensure the code form has been shown at least once
        self._ensure_code_form_open()
        fields = {"payload": json.dumps(payload, ensure_ascii=False)}
        return self._client.send_formspec_response("miney:code_form", fields)

    def _ensure_code_form_open(self) -> None:
        """
        Ensure the server has shown the 'miney:code_form' once.
        This uses a chat command and a Miney-local readiness flag to avoid
        relying on Lua component initialization order.
        """
        if not self._client or not self._client.state.authenticated:
            return
        if self._code_form_shown:
            return
        if not self._code_form_warmup_sent:
            ok = self._client.send_chat_message("/miney form")
            if ok:
                logger.debug("Requested code form warm-up via chat command.")
            self._code_form_warmup_sent = True
        deadline = time.time() + 2.0
        while not self._code_form_shown and time.time() < deadline:
            time.sleep(0.05)


    def _dispatch_loop(self) -> None:
        """Deliver events to registered handlers asynchronously."""
        while self._running:
            try:
                event = self._events_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                # Use the Event object's attributes
                if event.name in self.SUPPORTED_EVENTS:
                    for cb in list((self._event_handlers.get(event.name) or {}).values()):
                        try:
                            cb(event)
                        except Exception as e:
                            logger.error("Error in '%s' handler: %s", event.name, e, exc_info=True)
                elif isinstance(event, ChatCommandEvent):
                    # Access the command name directly from the event object
                    name = event.command_name
                    handler = self._command_handlers.get(name)
                    if handler:
                        try:
                            handler(event)
                        except Exception as e:
                            logger.error("Error in chatcommand handler '%s': %s", name, e, exc_info=True)
            finally:
                self._events_queue.task_done()

    def _handle_miney_callbacks(self, formspec: str) -> None:
        """Handle incoming JSON from the miney:callbacks channel."""
        self._code_form_shown = True

        try:
            data = json.loads(formspec)
        except json.JSONDecodeError:
            logger.warning("Received non-JSON callbacks formspec payload.")
            return

        # Ignore Lua execution results routed on the same form
        if isinstance(data, dict) and ("execution_id" in data or "result" in data):
            return

        if data is None:
            logger.debug("Received initial/empty callbacks message; marking ready and ignoring.")
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
            self._events_queue.put(event_obj)
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

        :param event: The name of the event to subscribe to.
        :param parameters: Optional filters for the event subscription.
        :return: The decorator function.
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
        :param parameters: Optional filters for the event subscription.
        :return: A unique token for this registration.
        """
        if event not in self.SUPPORTED_EVENTS:
            raise ValueError(
                f"Event '{event}' is not supported. "
                f"Supported events are: {sorted(list(self.SUPPORTED_EVENTS))}"
            )
        if not callable(callback):
            raise ValueError("callback must be callable")
        token = str(uuid.uuid4())
        self._event_handlers.setdefault(event, {})[token] = callback

        # Only register with server when this is the first handler for the event
        if len(self._event_handlers[event]) == 1:
            payload: Dict[str, Any] = {
                "action": "register",
                "events": [event],
                "client_id": self._client_id,
            }
            if parameters:
                payload["filters"] = parameters
            self._send(payload)
            logger.info("Registered event subscription for '%s'", event)

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
        if removed_key:
            handlers.pop(removed_key, None)

        if handlers and len(handlers) > 0:
            return

        # If no handlers remain, unregister from server
        self._event_handlers.pop(event, None)
        self._send({"action": "unregister", "events": [event], "client_id": self._client_id})
        logger.info("Unregistered event subscription for '%s'", event)

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

            # Unregister event subscriptions
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
