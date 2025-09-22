from typing import TYPE_CHECKING, Callable, Optional, Dict, Any
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
    """Register callbacks inside Luanti, to receive events from Lua"""
    def __init__(self, luanti: 'Luanti'):
        self.lt = luanti
        self._client = luanti.luanti
        self._client_id: str = str(uuid.uuid4())
        self._event_handlers: Dict[str, Dict[str, Callable[[Dict[str, Any]], None]]] = {}
        self._command_handlers: Dict[str, Callable[[Dict[str, Any]], None]] = {}
        self._events_queue: "queue.Queue[Dict[str, Any]]" = queue.Queue()
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
                ev_name = event.get("event")
                if ev_name == "chat_message":
                    for cb in list((self._event_handlers.get("chat_message") or {}).values()):
                        try:
                            cb(event)
                        except Exception as e:
                            logger.error("Error in chat_message handler: %s", e, exc_info=True)
                elif ev_name == "chatcommand":
                    payload = event.get("payload") or {}
                    name = payload.get("name")
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
            self._events_queue.put(data)
            logger.debug("Queued event %s for dispatch", data.get("event"))
            return

        logger.debug("Unhandled callbacks payload: %s", data)

    def activate(self, event: str, callback: Callable[[Dict[str, Any]], None],
                 parameters: Optional[Dict[str, Any]] = None) -> str:
        """
        Register a callback for an event.

        Returns a token that can be used to deactivate.
        """
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

    def deactivate(self, event: str, token_or_callback: Any) -> None:
        """
        Deactivate an event subscription by token or callback function.
        """
        handlers = self._event_handlers.get(event)
        if not handlers:
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

    def register_command(self, name: str, callback: Callable[[Dict[str, Any]], None],
                         params: str = "", description: str = "",
                         privileges: Optional[Dict[str, bool]] = None) -> str:
        """
        Register a chat command; callback receives the full event dict.
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
        """Unregister a previously registered chat command."""
        if not name or name not in self._command_handlers:
            return
        self._send({"action": "unregister_chatcommand", "name": name, "client_id": self._client_id})
        self._command_handlers.pop(name, None)
        logger.info("Unregistered chat command '%s'", name)

    def next_event(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Blocking poll for next event copy. Returns None on timeout.
        """
        try:
            return self._events_queue.get(timeout=timeout)
        except queue.Empty:
            return None

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
