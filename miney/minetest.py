import socket
import json
import math
from typing import Dict, Union
import time
import string
from random import choices
import miney


class Minetest:
    """__init__([server, playername, password, [port]])
    The Minetest server object. All other objects are accessable from here. By creating an object you connect to Minetest.

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
    def __init__(self, server: str = "127.0.0.1", playername: str = None, password: str = "", port: int = 29999):
        """
        Connect to the minetest server.

        :param server: IP or DNS name of an minetest server with installed apisocket mod
        :param port: The apisocket port, defaults to 29999
        """
        self.server = server
        self.port = port
        if playername:
            self.playername = playername
        else:
            self.playername = miney.default_playername
        self.password = password

        # setup connection
        self.connection = None
        self._connect()

        self.event_queue = []  # List for collected but unprocessed events
        self.result_queue = {}  # List for unprocessed results
        self.callbacks = {}

        self.clientid = None  # The clientid we got from mineysocket after successful authentication
        self._authenticate()

        # objects representing local properties
        self._lua: miney.lua.Lua = miney.Lua(self)
        self._chat: miney.chat.Chat = miney.Chat(self)
        self._node: miney.node.Node = miney.Node(self)

        player = self.lua.run(
            """
            local players = {}
            for _,player in ipairs(minetest.get_connected_players()) do
                table.insert(players,player:get_player_name())
            end
            return players
            """
        )
        if player:
            player = [] if len(player) == 0 else player
        else:
            raise miney.DataError("Received malformed player data.")

        self._player = miney.PlayerIterable(self, player)

        self._tools_cache = self.lua.run(
            """
            local nodes = {}
            for name, def in pairs(minetest.registered_tools) do
                table.insert(nodes, name)
            end return nodes
            """
        )
        self._tool = miney.ToolIterable(self, self._tools_cache)

    def _connect(self):
        # setup connection
        self.connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.connection.settimeout(2.0)
        self.connection.connect((self.server, self.port))

    def _authenticate(self):
        """
        Authenticate to mineysocket.

        :return: None
        """
        # authenticate
        self.send({"playername": self.playername, "password": self.password})
        result = self.receive("auth")

        if result:
            if "auth_ok" not in result:
                raise miney.AuthenticationError("Wrong playername or password")
            else:
                self.clientid = result[1]  # Clientid = <IP>:<Port>
        else:
            raise miney.DataError("Unexpected authentication result.")

    def send(self, data: Dict):
        """
        Send json objects to the miney-socket.

        :param data:
        :return:
        """
        chunk_size = 4096
        raw_data: bytes = str.encode(json.dumps(data) + "\n")

        try:
            if len(raw_data) < chunk_size:
                self.connection.sendall(raw_data)
            else:  # we need to break the message in chunks
                for i in range(0, int(math.ceil((len(raw_data)/chunk_size)))):
                    self.connection.sendall(
                        raw_data[i * chunk_size:chunk_size + (i * chunk_size)]
                    )
                    time.sleep(0.01)  # Give luasocket a chance to read the buffer in time
                    # todo: Protocol change, that every chunked message needs a response before sending the next
        except ConnectionAbortedError:
            self._connect()
            self.send(data)

    def receive(self, result_id: str = None, timeout: float = None) -> Union[str, bool]:
        """
        Receive data and events from minetest.

        With an optional result_id this function waits for a result with that id by call itself until the right result
        was received. **If lua.run() was used this is not necessary, cause miney already takes care of it.**

        With the optional timeout the blocking waiting time for data can be changed.

        :Example to receive and print all events:

            >>> while True:
            >>>     print("Event received:", mt.receive())

        :param str result_id: Wait for this result id
        :param float timeout: Block further execution until data received or timeout in seconds is over.
        :rtype: Union[str, bool]
        :return: Data from mineysocket
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
        # Without a result_id we run an event callback
        elif not result_id and len(self.event_queue):
            result = self.event_queue[0]
            del self.event_queue[0]
            self._run_callback(result)
        try:
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
                raise miney.LuaResultTimeout()
    
            # process data
            if "result" in data:
                if result_id:  # do we need a specific result?
                    if data["id"] == result_id:  # we've got the result we wanted
                        return format_result(data)
                # We store this for later processing
                self.result_queue[data["id"]] = data
            elif "error" in data:
                if data["error"] == "authentication error":
                    if self.clientid:
                        # maybe a server restart or timeout. We just reauthenticate.
                        self._authenticate()
                        raise miney.SessionReconnected()
                    else:  # the server kicked us
                        raise miney.AuthenticationError("Wrong playername or password")
                else:
                    raise miney.LuaError("Lua-Error: " + data["error"])
            elif "event" in data:
                self._run_callback(data)
    
            # if we don't got our result we have to receive again
            if result_id:
                self.receive(result_id)

        except ConnectionAbortedError:
            self._connect()
            self.receive(result_id, timeout)

    def on_event(self, name: str, callback: callable) -> None:
        """
        Sets a callback function for specific events.

        :param name: The name of the event
        :param callback: A callback function
        :return: None
        """
        # Match answer to request
        result_id = ''.join(choices(string.ascii_lowercase + string.ascii_uppercase + string.digits, k=6))
        self.callbacks[name] = callback
        self.send({'activate_event': {'event': name}, 'id': result_id})

    def _run_callback(self, data: dict):
        if data['event'] in self.callbacks:
            # self.callbacks[data['event']](**data['event']['params'])
            if type(data['params']) is dict:
                self.callbacks[data['event']](**data['params'])
            elif type(data['params']) is list:
                self.callbacks[data['event']](*data['params'])

    @property
    def chat(self):
        """
        Object with chat functions.

        :Example:

            >>> mt.chat.send_to_all("My chat message")

        :return: :class:`miney.Chat`: chat object
        """
        return self._chat

    @property
    def node(self):
        """
        Manipulate and get information's about nodes.

        :return: :class:`miney.Node`: Node manipulation functions
        """
        return self._node

    def log(self, line: str):
        """
        Write a line in the servers logfile.

        :param line: The log line
        :return: None
        """
        return self.lua.run('minetest.log("action", "{}")'.format(line))

    @property
    def player(self):
        """
        Get a single players object.

        :Examples:

        Make a player 5 times faster:

            >>> mt.player.MyPlayername.speed = 5

        Use a playername from a variable:

            >>> player = "MyPlayername"
            >>> mt.player[player].speed = 5

        Get a list of all players

            >>> list(mt.player)
            [<minetest player "MineyPlayer">, <minetest player "SecondPlayer">, ...]

        :return: :class:`miney.Player`: Player related functions
        """
        return self._player

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
    def time_of_day(self, value: float):
        if 0 <= value <= 1:
            self.lua.run("return minetest.set_timeofday({})".format(value))
        else:
            raise ValueError("Time value has to be between 0 and 1.")

    @property
    def settings(self) -> dict:
        """
        Receive all server settings defined in "minetest.conf".

        :return: A dict with all non-default settings.
        """
        return self.lua.run("return minetest.settings:to_table()")

    @property
    def tool(self) -> 'miney.ToolIterable':
        """
        All available tools in the game, sorted by categories. In the end it just returns the corresponding
        minetest tool string, so `mt.tool.default.axe_stone` returns the string 'default:axe_stone'.
        It's a nice shortcut in REPL, cause with auto completion you have only pressed 2-4 keys to get to your type.

        :Examples:

            Directly access a tool:

            >>> mt.tool.default.pick_mese
            'default:pick_mese'

            Iterate over all available types:

            >>> for tool_type in mt.tool:
            >>>     print(tool_type)
            default:shovel_diamond
            default:sword_wood
            default:shovel_wood
            ... (there should be around 34 different tools)
            >>> print(len(mt.tool))
            34

            Get a list of all types:

            >>> list(mt.tool)
            ['default:pine_tree', 'default:dry_grass_5', 'farming:desert_sand_soil', ...

            Add a diamond pick axe to the first player's inventory:

            >>> mt.player[0].inventory.add(mt.tool.default.pick_diamond, 1)

        :rtype: :class:`ToolIterable`
        :return: :class:`ToolIterable` object with categories. Look at the examples above for usage.
        """
        return self._tool

    def __del__(self) -> None:
        """
        Close the connection to the server.

        :return: None
        """
        self.connection.close()

    def __repr__(self):
        return '<minetest server "{}:{}">'.format(self.server, self.port)

    def __delete__(self, instance):
        self.connection.close()
