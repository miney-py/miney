import logging
from dataclasses import dataclass
from functools import cached_property
from typing import Any, Dict, Optional, Callable

from .chat import Chat
from .events import Event
from .lua import Lua
from .callback import Callback
from .luanticlient import LuantiClient
from .luanticlient.exceptions import LuantiConnectionError
from .nodes import Nodes
from .player import PlayerIterable
from .tool import ToolIterable


logger = logging.getLogger(__name__)

default_playername = "miney"


@dataclass
class GameInfo:
    """
    Holds information about the current game.

    This dataclass provides both attribute-style and dictionary-style access
    to the game's properties.
    """
    id: str
    title: str
    author: str
    path: str

    def __getitem__(self, key: str):
        """
        Allows dictionary-style access to attributes.

        :param key: The attribute name.
        :return: The value of the attribute.
        """
        return getattr(self, key)


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

    def __init__(self, server: str = "127.0.0.1", playername: str = None, password: str = "ChangeThePassword!", port: int = 30000, invisible: bool = True):
        """
        Connect to the Luanti server.

        :param server: IP or DNS name of an Luanti server with installed miney mod
        :param port: The apisocket port, defaults to 29999
        :param invisible: If True, makes the Miney player invisible and grants creative privilege to be safe from mobs.
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
        self._callbacks: Callback = Callback(self)

        # objects representing local properties
        self._lua: Lua = Lua(self.luanti)
        self._chat: Chat = Chat(self)
        self._nodes: Nodes = Nodes(self)

        self._tools_cache = self.lua.run(
            """
            local node = {}
            for name, def in pairs(minetest.registered_tools) do
                table.insert(node, name)
            end return node
            """
        )
        self._tool = ToolIterable(self, self._tools_cache)

        # Optionally make player invisible and grant creative privilege
        if invisible:
            try:
                player_obj = self.players[self.playername]
                player_obj.invisible = True
                player_obj.creative = True
            except Exception as e:
                logger.error(f"Failed to set invisible/creative for player '{self.playername}': {e}")

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
        self.disconnect()

    def on_event(self, name: str, run: Callable[[Event], None], parameters: Optional[Dict[str, Any]] = None) -> None:
        """
        Register an event callback without using a decorator.

        This is a procedural alternative to the ``@lt.callbacks.on()`` decorator.

        :param name: The name of the event to subscribe to (e.g., "chat_message").
        :param run: The function to execute when the event occurs. It will receive an Event object.
        :param parameters: Optional filters for the event subscription.
        """
        if not callable(run):
            raise ValueError("run must be callable")
        self._callbacks.register(name, run, parameters=parameters)
        logger.info("Registered event subscription for '%s'", name)

    def off_event(self, name: str, run: Callable[[Event], None]) -> None:
        """
        Unregister a previously registered event callback.

        :param name: The name of the event the callback is subscribed to.
        :param run: The function reference of the callback to unregister.
        """
        self._callbacks.unregister(name, run)
        logger.info("Unregistered event subscription for '%s'", name)

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
    def nodes(self):
        """
        Provides access to node manipulation functions.

        See :class:`~miney.nodes.Nodes` for a full list of methods.

        :return: :class:`~miney.nodes.Nodes`
        """
        return self._nodes

    @property
    def callbacks(self) -> 'Callback':
        """
        Provides access to the callback manager.

        See :class:`~miney.callback.Callback` for the available methods.
        """
        return self._callbacks

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

    @cached_property
    def game_info(self) -> 'GameInfo':
        """
        Get information about the current game.

        This property returns an object providing details about the game running on the server.

        :Example:

            >>> game = lt.game_info
            >>> print(game.id)
            'mineclone2'
            >>> print(game.title)
            'VoxeLibre'
            >>> print(game['author'])
            'Wuzzy'

        :return: A :class:`~miney.luanti.GameInfo` object.
        """
        info_dict = self.lua.run("return minetest.get_game_info()")
        return GameInfo(**info_dict)

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
        Shuts down all services and disconnects from the Luanti server.

        This method automatically unregisters all event callbacks and chat commands
        before closing the network connection to ensure a clean shutdown. It is
        called automatically when the object is deleted or when exiting a 'with'
        block.
        """
        # Best-effort cleanup of registered callbacks before dropping the connection
        if hasattr(self, "_callbacks") and self._callbacks:
            try:
                self._callbacks.shutdown()
            except Exception as e:
                logger.error(f"Error during callback shutdown: {e}")

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
