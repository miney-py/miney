from typing import Dict
import miney


class Chat:
    """
    Chat functions.
    """
    def __init__(self, mt: miney.Minetest):
        self.mt = mt

    def __repr__(self):
        return '<minetest chat functions>'

    def send_to_all(self, message: str) -> None:
        """
        Send a chat message to all connected players.

        :param message: The chat message
        :return: None
        """
        self.mt.lua.run("minetest.chat_send_all('{}')".format(message.replace("\'", "\\'")))

    def send_to_player(self, playername: str, message: str):
        return self.mt.lua.run("return minetest.chat_send_player({}, {}})".format(playername, message))

    def format_message(self, playername: str, message: str):
        return self.mt.lua.run("return minetest.format_chat_message({}}, {}})".format(playername, message))

    def registered_commands(self):
        return self.mt.lua.run("return minetest.registered_chatcommands")

    def register_command(self, name, parameter: str, callback_function, description: str = "", privileges: Dict = None):

        if isinstance(callback_function, callable):
            pass
        elif isinstance(callback_function, str):
            pass

        return self.mt.lua.run(
            """
            return minetest.register_chatcommand(
                {name}, 
                {{params = {params}, description={description}, privs={privs}, func={func}}
            )""".format(
                name=name,
                params=parameter,
                description=description,
                privs=self.mt.lua.dumps(privileges) if privileges else "{}",
                func=callback_function
            )
        )

    def override_command(self, definition):
        pass

    def unregister_command(self, name: str):
        return self.mt.lua.run("return minetest.register_chatcommand({})".format(name))
