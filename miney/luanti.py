import logging
from typing import TYPE_CHECKING

from .chat import Chat
from .inventory import Inventory
from .lua import Lua
from .luanticlient import LuantiClient
from .luanticlient.exceptions import LuantiConnectionError
from .nodes import Nodes
from .player import PlayerIterable
from .tool import ToolIterable


logger = logging.getLogger(__name__)

default_playername = "miney"


class Luanti:
    """__init__([server, playername, password, [port]])
    The Miney server object. All other objects are accessable from here. By creating an object you connect to Luanti.

    **Parameters aren't required, if you run miney and Luanti on the same computer.**

    Miney connects as player with the playername you provided and also registers this player to the server with the password.

    If you connect with miney the first time to the luanti server outside your computer (something else than 127.0.0.1),
    you need to give the miney player the "miney" priviledge.
    Do that by opening the chat (with the T key) and type `/priv miney miney` (`/priv <player_name> <privledge>`).

    *If you connect over LAN or Internet to a Luanti server with installed miney mod, you should use a strong password!
    The miney mod allows this player to run commands and scripts; this could be abused if you choose a weak password!*

    ::

        >>> lt = Luanti("luantiserver.in.the.internet.com", "ChatBot", "SuperSecretPasswordNobodyWouldKnowCauseItsRandom!")

    Account creation is done by starting Luanti and connect to a server with a playername
    and password. https://docs.luanti.org/for-players/getting-started/#play-online

    :param str server: IP or DNS name of an Luanti server with installed miney mod
    :param str playername: A name to identify yourself to the server. Default is "Miney".
    :param str password: Your password
    :param int port: The apisocket port, defaults to 29999
    """

    def __init__(self, server: str = "127.0.0.1", playername: str = None, password: str = "ChangeThePassword!", port: int = 30000):
        """
        Connect to the Luanti server.

        :param server: IP or DNS name of an Luanti server with installed miney mod
        :param port: The apisocket port, defaults to 29999
        """
        self.server = server
        self.port = port
        if playername:
            self.playername = playername
        else:
            self.playername = default_playername
        self.password = password

        # setup connection
        self.luanti = LuantiClient(playername=self.playername, password=self.password, host=self.server, port=self.port)
        try:
            self.luanti.connect()
        except LuantiConnectionError as e:
            if e.reason_code == 1:
                logger.warning(f"Login failed for user '{self.playername}'. The server suggests registration. Attempting to register as a new user.")
                self.luanti.disconnect()  # Ensure clean state

                # Re-initialize and attempt to register
                self.luanti = LuantiClient(playername=self.playername, password=self.password, host=self.server,
                                                 port=self.port)
                try:
                    self.luanti.connect(register=True)
                    logger.warning(f"Successfully registered and connected as new user '{self.playername}'.")
                    logger.warning("This new user might not have the required 'miney' privilege.")
                    logger.warning(f"To grant it, run this command on the server: /grant {self.playername} miney")
                except LuantiConnectionError as e2:
                    logger.error(f"Automatic registration failed: {e2}")
                    logger.error("This probably means the user already exists and the initial password was incorrect, or the server does not allow registration.")
                    raise e2  # Re-raise the registration error
            else:
                # For any other connection error, just re-raise it.
                raise e

        self.result_queue = {}  # List for unprocessed results
        self.callbacks = {}

        # objects representing local properties
        self._lua: Lua = Lua(self.luanti)
        self._chat: Chat = Chat(self)
        self._nodes: Nodes = Nodes(self)
        self._inventory: Inventory = Inventory(self, None)

        self._tools_cache = self.lua.run(
            """
            local node = {}
            for name, def in pairs(minetest.registered_tools) do
                table.insert(node, name)
            end return node
            """
        )
        self._tool = ToolIterable(self, self._tools_cache)

    def __enter__(self):
        """
        Enter the runtime context related to this object.

        :return: The Luanti instance.
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit the runtime context and disconnect from the server.
        """
        if self.luanti:
            self.luanti.disconnect()

    def on_event(self, name: str, run: callable) -> None:
        """
        Sets a callback function for specific events.

        :param name: The name of the event
        :param run: A callback function
        :return: None
        """
        # TODO Implement Callbacks
        logger.warning("Callbacks are not yet implemented.")

    @property
    def chat(self):
        """
        Provides access to chat functions.

        See :class:`~miney.chat.Chat` for a full list of methods.

        :Example:

            >>> lt.chat.send_to_all("My chat message")

        :return: :class:`~miney.chat.Chat`
        """
        return self._chat

    @property
    def inventory(self):
        """
        Provides access to inventory functions.

        .. note::
           This property is a bit different. To access a specific inventory, you must
           first get a player or node object.

           >>> player_inventory = lt.players.MyPlayer.inventory
           >>> chest_inventory = lt.nodes.get(Point(0, 0, 0)).inventory

        See :class:`~miney.inventory.Inventory` for a full list of methods.

        :return: :class:`~miney.inventory.Inventory`
        """
        # The parent is set to None here because the actual parent (player/node)
        # is determined when the inventory is accessed from that object.
        self._inventory.parent = None
        return self._inventory

    @property
    def nodes(self):
        """
        Provides access to node manipulation functions.

        See :class:`~miney.nodes.Nodes` for a full list of methods.

        :return: :class:`~miney.nodes.Nodes`
        """
        return self._nodes

    def log(self, line: str):
        """
        Write a line in the servers logfile.

        :param line: The log line
        :return: None
        """
        return self.lua.run('minetest.log("action", "{}")'.format(line))

    @property
    def players(self) -> 'PlayerIterable':
        """
        Provides access to online players.

        This property returns an iterable object that allows access to individual
        :class:`~miney.player.Player` instances.

        :Examples:

        Make a player 5 times faster:

            >>> lt.players.MyPlayername.speed = 5

        Get a list of all players:

            >>> list(lt.players)
            [<Luanti Player "MineyPlayer">, <Luanti Player "SecondPlayer">, ...]

        :return: An iterable object for players.
        """
        player_names = self.lua.run(
            """
            local players = {}
            for _,player in ipairs(minetest.get_connected_players()) do
                table.insert(players,player:get_player_name())
            end
            return players
            """
        )
        if not player_names:
            player_names = []

        return PlayerIterable(self, player_names)

    @property
    def lua(self):
        """
        Provides access to functions for running raw Lua code on the server.

        See :class:`~miney.lua.Lua` for a full list of methods.

        :return: :class:`~miney.lua.Lua`
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
    def version(self) -> str:
        """
        Get the server version string.

        :return: The server version string (e.g., "5.13.0").
        """
        version_info = self.lua.run("return minetest.get_version()")
        return version_info.get("string", "N/A")

    @property
    def tool(self) -> 'ToolIterable':
        """
        Provides an iterable helper for accessing all available tool types.

        This is a shortcut for getting tool item strings with IDE auto-completion.
        See :class:`~miney.tool.ToolIterable` for more details.

        :Examples:

            >>> lt.tool.default.pick_mese
            'default:pick_mese'

            >>> lt.players[0].inventory.add(lt.tool.default.pick_diamond, 1)

        :return: An iterable object for tool types.
        """
        return self._tool

    def disconnect(self):
        """
        Disconnect from the Luanti server.

        This method is called automatically when the object is deleted or when exiting a 'with' block.
        It ensures that the connection is properly closed.
        """
        if self.luanti:
            self.luanti.disconnect()
            self.luanti = None

    def __del__(self) -> None:
        """
        Destructor for Luanti.

        .. note::
            Using a 'with' statement is the recommended way to ensure
            a clean disconnection, as calling disconnect during interpreter
            shutdown is not reliable.
        """
        # Only attempt to disconnect if the connection seems to be active.
        if hasattr(self, 'luanti') and self.luanti and self.luanti.connection and self.luanti.connection.running:
            self.luanti.disconnect()

    def __repr__(self):
        return '<Luanti server "{}:{}">'.format(self.server, self.port)
