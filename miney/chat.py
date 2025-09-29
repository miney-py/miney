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

        This is a non-decorator way to register commands. For a more modern and
        readable approach, consider using the :func:`~miney.chat.Chat.command`
        decorator instead.

        :param name: The name of the command.
        :param callback_function: The function to call when the command is executed.
        :param parameter: The command's parameter string (for /help).
        :param description: The command's description (for /help).
        :param privileges: Privileges required to execute the command.
        :return: The command name.
        """
        return self.lt.callbacks.register_command(
            name=name,
            callback=callback_function,
            params=parameter,
            description=description,
            privileges=privileges or {},
        )

    def command(
        self,
        name: str,
        parameter: str = "",
        description: str = "",
        privileges: Dict | None = None,
    ) -> Callable:
        """
        Decorator to register a chat command.

        This is the recommended way to register chat commands.

        .. code-block:: python

            from miney.events import ChatCommandEvent

            @lt.chat.command("hello", description="Greets the player")
            def hello_command(event: ChatCommandEvent):
                lt.chat.send_to_player(event.issuer, f"Hello, {event.issuer}!")

        :param name: The name of the command.
        :param parameter: The command's parameter string (for /help).
        :param description: The command's description (for /help).
        :param privileges: Privileges required to execute the command.
        :return: The decorator function.
        """
        return self.lt.callbacks.command(name, parameter, description, privileges)

    def on(self, event: str = "chat_message", filters: Optional[Dict[str, Any]] = None) -> Callable:
        """
        Decorator to subscribe to chat-related events.

        The default and most common event is 'chat_message'. The callback receives the
        full event dictionary as produced by the Miney mod.

        .. code-block:: python

            from miney.events import ChatMessageEvent

            @lt.chat.on()  # Defaults to "chat_message"
            def on_chat(event: ChatMessageEvent):
                print(f"{event.sender_name}: {event.message}")

        :param event: The name of the event to subscribe to. Defaults to 'chat_message'.
        :param filters: Optional filters for the event subscription.
        :return: The decorator function.
        """
        if event != "chat_message":
            logger.warning(
                "Registering a handler for event '%s' via Chat.on(). "
                "Consider using `Luanti.callbacks.on()` for non-chat events.",
                event,
            )
        return self.lt.callbacks.on(event, filters)

    def on_unregister(self, callback: Callable[[dict], None], event: str = "chat_message") -> None:
        """
        Unregister a previously registered event callback.

        :param callback: The callback function to unregister.
        :param event: The name of the event. Defaults to 'chat_message'.
        """
        self.lt.callbacks.unregister(event, callback)
        logger.info("Unregistered callback for event '%s'", event)

    def unregister_command(self, name: str):
        """
        Unregister a chat command previously registered.
        """
        self.lt.callbacks.unregister_command(name)
