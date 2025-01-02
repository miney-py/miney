from typing import Dict, Union
import re
import logging
import miney


logger = logging.getLogger(__name__)

class Chat:
    """
    Chat functions.
    """
    def __init__(self, luanti: miney.Luanti):
        self.lt = luanti

    def __repr__(self):
        return '<Luanti Chat>'

    def send_to_all(self, message: str) -> None:
        """
        Send a chat message to all connected players.

        :param message: The chat message
        :return: None
        """
        self.lt.lua.run("minetest.chat_send_all('{}')".format(message.replace("\'", "\\'")))

    def send_to_player(self, player: Union[str, miney.Player], message: str) -> None:
        """
        Send a message to a player.

        :Send "Hello" to the first player on the server:

        >>> lt.chat.send_to_player(lt.player[0], "Hello")

        :Send "Hello" to the player "Luanti" on the server:

        >>> lt.chat.send_to_player("Luanti", "Hello")

        :param player: A Player object or a string with the name.
        :param message: The message
        :return: None
        """
        if isinstance(player, miney.Player):
            player = player.name
        message = message.replace("\"", "'")  # replace " with '
        # todo: Find a solution to support " again without breaking security.
        self.lt.lua.run("return minetest.chat_send_player(\"{}\", \"{}\")".format(player, message))

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
