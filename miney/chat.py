from typing import Dict, Union, TYPE_CHECKING
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

        :param message: The chat message
        :return: None
        """
        self.lt.lua.run(f"minetest.chat_send_all({self.lt.lua.dumps(message)})")

    def send_to_player(self, player: Union[str, Player], message: str) -> None:
        """
        Send a message to a player.

        :Send "Hello" to the first player on the server:

        >>> lt.chat.send_to_player(lt.players[0], "Hello")

        :Send "Hello" to the player "Luanti" on the server:

        >>> lt.chat.send_to_player("Luanti", "Hello")

        :param player: A Player object or a string with the name.
        :param message: The message
        :return: None
        """
        if isinstance(player, Player):
            player = player.name
        self.lt.lua.run(f"return minetest.chat_send_player({self.lt.lua.dumps(player)}, {self.lt.lua.dumps(message)})")

    def format_message(self, playername: str, message: str):
        return self.lt.lua.run("return minetest.format_chat_message({}, {})".format(playername, message))

    def register_command(self, name, callback_function, parameter: str = "", description: str = "", privileges: Dict = None):
        # TODO: Reimplement this function
        logger.warning("Registering commands is not yet implemented")
        pass

    def override_command(self, definition):
        pass

    def unregister_command(self, name: str):
        return self.lt.lua.run("return minetest.register_chatcommand({})".format(name))
