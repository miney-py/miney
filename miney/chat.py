from typing import Dict, Union
import re
import miney


class Chat:
    """
    Chat functions.
    """
    def __init__(self, mt: miney.Minetest):
        self.mt = mt

    def __repr__(self):
        return '<minetest Chat>'

    def send_to_all(self, message: str) -> None:
        """
        Send a chat message to all connected players.

        :param message: The chat message
        :return: None
        """
        self.mt.lua.run("minetest.chat_send_all('{}')".format(message.replace("\'", "\\'")))

    def send_to_player(self, player: Union[str, miney.Player], message: str) -> None:
        """
        Send a message to a player.

        :Send "Hello" to the first player on the server:

        >>> mt.chat.send_to_player(mt.player[0], "Hello")

        :Send "Hello" to the player "Miney" on the server:

        >>> mt.chat.send_to_player("Miney", "Hello")

        :param player: A Player object or a string with the name.
        :param message: The message
        :return: None
        """
        if isinstance(player, miney.Player):
            player = player.name
        message = message.replace("\"", "'")  # replace " with '
        # todo: Find a solution to support " again without breaking security.
        self.mt.lua.run("return minetest.chat_send_player(\"{}\", \"{}\")".format(player, message))

    def format_message(self, playername: str, message: str):
        return self.mt.lua.run("return minetest.format_chat_message({}, {})".format(playername, message))

    def register_command(self, name, callback_function, parameter: str = "", description: str = "", privileges: Dict = None):
        self.mt.lua.run(
            f"""
            minetest.register_chatcommand(
                "{name}", 
                {{func = function(name, param) 
                    mineysocket.send_event({{ event = {{ "chatcommand_{name}", name, param }} }})
                    return true, ""
                end,}}
            )
            """)
        self.mt.on_event(f"chatcommand_{name}", callback_function)

    def override_command(self, definition):
        pass

    def unregister_command(self, name: str):
        return self.mt.lua.run("return minetest.register_chatcommand({})".format(name))
