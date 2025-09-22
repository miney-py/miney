from typing import Any, Callable, Dict, Optional, Union, TYPE_CHECKING
import logging
from .player import Player
if TYPE_CHECKING:
    from .luanti import Luanti


logger = logging.getLogger(__name__)

class Chat:
    """
    Chat functions.
    """
    def __init__(self, luanti: 'Luanti'):
        self.lt = luanti

    def __repr__(self):
        return '<Luanti Chat>'

    def send_to_all(self, message: str) -> None:
        """
        Send a chat message to all connected players.
        """
        if not isinstance(message, str):
            logger.warning("Coercing chat message to string; received %s", type(message).__name__)
            message = str(message)
        self.lt.lua.run(f"minetest.chat_send_all({self.lt.lua.dumps(message)})")

    def send_to_player(self, player: Union[str, Player], message: str) -> None:
        """
        Send a message to a player.
        """
        if isinstance(player, Player):
            player = player.name
        elif not isinstance(player, str):
            raise TypeError(f"Parameter 'player' must be str or Player, got {type(player).__name__}")

        if not isinstance(message, str):
            logger.warning("Coercing chat message to string; received %s", type(message).__name__)
            message = str(message)

        self.lt.lua.run(
            f"return minetest.chat_send_player({self.lt.lua.dumps(player)}, {self.lt.lua.dumps(message)})"
        )

    def format_message(self, playername: str, message: str):
        return self.lt.lua.run("return minetest.format_chat_message({}, {})".format(playername, message))

    def register_command(
        self,
        name: str,
        callback_function: callable,
        parameter: str = "",
        description: str = "",
        privileges: Dict | None = None,
    ):
        """
        Register a chat command handled by the Python client.

        This is the primary entry point for chat commands in Miney. Prefer using this
        method over low-level Callback.register_command().

        Returns the command name (for convenience).
        """
        return self.lt.callbacks.register_command(
            name=name,
            callback=callback_function,
            params=parameter,
            description=description,
            privileges=privileges or {},
        )

    def on_message(self, callback: Callable[[dict], None], filters: Optional[Dict[str, Any]] = None) -> None:
        """
        Register a callback for incoming chat messages.

        The callback receives the full event dictionary as produced by the Miney mod
        (event='chat_message', payload contains 'name' and 'message').
        """
        if not callable(callback):
            raise ValueError("callback must be callable")
        self.lt.callbacks.activate("chat_message", callback, parameters=filters)
        logger.info("Registered chat message callback")

    def off_message(self, callback: Callable[[dict], None]) -> None:
        """
        Unregister a previously registered chat message callback by function reference.
        """
        self.lt.callbacks.deactivate("chat_message", callback)
        logger.info("Unregistered chat message callback")

    def unregister_command(self, name: str):
        """
        Unregister a chat command previously registered.
        """
        self.lt.callbacks.unregister_command(name)
