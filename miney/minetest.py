import socket
import json
from typing import Dict
import miney


class Minetest:
    """__init__([server, playername, password, [port]])
    The Minetest server object. All other object are created from here. By creating an object you connect to Minetest.

    **Parameters aren't required, if you run miney and minetest on the same computer.**

    *If you connect over LAN or Internet to a Minetest server with installed mineysocket, you have to provide a valid
    playername with a password:*

    ::

        >>> mt = Minetest("192.168.0.2", "MyNick", "secret_password")

    Account creation is done by starting Minetest and connect to a server with a username
    and password. https://wiki.minetest.net/Getting_Started#Play_Online

    :param str server: IP or DNS name of an minetest server with installed apisocket mod
    :param str playername: A name to identify yourself to the server.
    :param str password: Your password
    :param int port: The apisocket port, defaults to 29999
    """
    def __init__(self, server: str = "127.0.0.1", playername: str = "Miney", password: str = "", port: int = 29999):
        """
        Connect to the minetest server.

        :param server: IP or DNS name of an minetest server with installed apisocket mod
        :param port: The apisocket port, defaults to 29999
        """
        self.server = server
        self.port = port
        self.playername = playername
        self.password = password
        self.connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.connection.settimeout(2.0)
        self.event_queue = []  # List for collected but unprocessed events
        self.result_queue = {}  # List for unprocessed results

        self._authenticate()

        # objects representing local properties
        self._lua: miney.lua.Lua = miney.Lua(self)
        self._chat: miney.chat.Chat = miney.Chat(self)
        self.node: miney.node.Node = miney.Node(self)
        """
        Manipulate and get information's about nodes.

        :return: :class:`miney.Node`: Node manipulation functions
        """

        self.player = PlayerIterable(self, self.players)
        """Get a single players object.
        
        :Example, that makes a player 5 times faster:
            
            >>> import miney
            >>> mt = miney.Minetest()
            >>> mt.player.MyPlayername.speed = 5
            
        :Example with a playername from a variable:
        
            >>> import miney
            >>> mt = miney.Minetest()
            >>> player = "MyPlayername"
            >>> mt.player[player].speed = 5
        
        """

    def _authenticate(self):
        """
        Authenticate to mineysocket.

        :return: None
        """
        # authenticate
        self.send({"playername": self.playername, "password": self.password})
        result = self.receive("auth")

        if "auth_ok" not in result:
            raise miney.AuthenticationError("Wrong playername or password")
        else:
            self.clientid = result[1]  # Clientid = <IP>:<Port>

    def send(self, data: Dict):
        """
        Send json objects to the miney-socket.

        :param data:
        :return:
        """
        self.connection.sendto(str.encode(json.dumps(data) + "\n"), (self.server, self.port))

    def receive(self, result_id: str = None, timeout: float = None):
        """
        Receive data and events from minetest.

        With an optional result_id this function waits for a result with that id by call itself until the right result
        was received. **If lua.run() was used this is not necessary, cause miney already takes care of it.**

        With the optional timeout the blocking waiting time for data can be changed.

        :Example to receive and print all events:

            >>> from miney import Minetest
            >>> mt = Minetest()
            >>>
            >>> while True:
            >>>     print("Event received:", mt.receive())

        :param str result_id: Wait for this result id
        :param float timeout: Block further execution until data received or timeout in seconds is over.
        :return:
        """

        def format_result(result_data):
            if type(result_data["result"]) in (list, dict):
                if len(result_data["result"]) == 0:
                    return
                if len(result_data["result"]) == 1:  # list with single element doesn't needs a list
                    return result_data["result"][0]
                if len(result_data["result"]) > 1:
                    return tuple(result_data["result"])
            else:
                return result_data["result"]

        # Check if we have to return something received earlier
        if result_id in self.result_queue:
            result = format_result(self.result_queue[result_id])
            del self.result_queue[result_id]
            return result
        elif not result_id and len(self.event_queue):
            result = self.event_queue[0]
            del self.event_queue[0]
            return result

        # Set a new timeout to prevent long waiting for a timeout
        if timeout:
            self.connection.settimeout(timeout)

        try:
            # receive the raw data and try to decode json
            data_buffer = b""
            while "\n" not in data_buffer.decode():
                data_buffer = data_buffer + self.connection.recv(4096)
            data = json.loads(data_buffer.decode())
        except socket.timeout:
            return False

        # process data
        if "result" in data:
            if result_id:  # do we need a specific result?
                if data["id"] == result_id:  # we've got the result we wanted
                    return format_result(data)
            # We store this for later processing
            self.result_queue[data["id"]] = data
        elif "error" in data:
            if data["error"] == "authentication error":
                # maybe a server restart or timeout. We just reauthenticate.
                self._authenticate()
                raise miney.SessionReconnected()
            else:
                raise miney.LuaError("Lua-Error: " + data["error"])
        elif "event" in data:
            # return event only if we don't want a specific result
            if not result_id:
                return data
            else:
                # We collect and store a event for later processing
                self.event_queue.append(data)

        # if we don't got our result we have to receive again
        if result_id:
            self.receive(result_id)

    @property
    def chat(self):
        """
        Object with chat functions.

        :Example:

            >>> import miney
            >>> mt = miney.Minetest()
            >>> mt.chat.send_to_all("My chat message")

        :return class:`minetest.Chat`: chat object
        """
        return self._chat

    def log(self, line: str):
        """
        Write a line in the servers logfile.

        :param line: The log line
        :return: None
        """
        return self.lua.run('minetest.log("action", "{}")'.format(line))

    @property
    def players(self):
        """
        Get a list of all connected players on minetest server.

        :return: List of players
        """
        data = self.lua.run(
            """
            local players = {}
            for _,player in ipairs(minetest.get_connected_players()) do
                table.insert(players,player:get_player_name())
            end
            return players
            """
        )
        data = [] if len(data) == 0 else data
        return data

    @property
    def lua(self):
        """
        Functions to run Lua inside Minetest.

        :return: :class:`miney.Lua`: Lua related functions
        """
        return self._lua

    @property
    def time_of_day(self) -> int:
        """
        Get and set the time of the day between 0 and 1, where 0 stands for midnight, 0.5 for midday.

        :return: time of day as float.
        """
        return self.lua.run("return minetest.get_timeofday()")

    @time_of_day.setter
    def time_of_day(self, value: int):
        self.lua.run("return minetest.set_timeofday({})".format(value))

    @property
    def settings(self) -> dict:
        """
        Receive all server settings defined in "minetest.conf".

        :return: A dict with all non-default settings.
        """
        return self.lua.run("return minetest.settings:to_table()")

    def close(self) -> None:
        """
        Close the connection to the server.

        :return: None
        """
        self.connection.close()

    def __repr__(self):
        return '<minetest server "{}:{}">'.format(self.server, self.port)

    def __delete__(self, instance):
        self.connection.close()


class PlayerIterable:
    """Player, implemented as iterable for easy autocomplete in the interactive shell"""
    def __init__(self, minetest: Minetest, online_players=None):
        if online_players:
            self.online_players = online_players
            self.mt = minetest

            # update list
            for player in online_players:
                self.__setattr__(player, miney.Player(minetest, player))

    def __iter__(self):
        player_object = []
        for player in self.online_players:
            player_object.append(miney.Player(self.mt, player))

        return iter(player_object)

    def __getitem__(self, item_key):
        if item_key in self.online_players:
            return self.__getattribute__(item_key)
        else:
            raise IndexError("unknown node type")

    def __len__(self):
        return len(self.online_players)
