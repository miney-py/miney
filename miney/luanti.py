import atexit
import logging
import weakref
from dataclasses import dataclass
from functools import cached_property
from typing import Any, Dict, Optional, Callable

from .assets import Assets
from .chat import Chat
from .events import Event
from .lua import Lua
from .callback import Callback
from .luanticlient import LuantiClient
from .luanticlient.exceptions import LuantiConnectionError
from .nodes import Nodes
from .player import PlayerIterable
from .storage import Storage
from .tool import ToolIterable
from .env import manage
from .env.paths import EnvPaths, find_env
from .env.state import WorldState, list_states, load_state
from .exceptions import MineyRunError


logger = logging.getLogger(__name__)

default_playername = "miney"


def _log_progress(progress: manage.Progress) -> None:
    """
    Send one autostart progress message to the log instead of the terminal.

    A library has no business printing, so everything the environment reports while
    a world is being started goes to logging. The one thing a beginner really needs
    to see - that Miney is starting a server and will be a moment - is printed by
    :class:`Luanti` itself, once.

    :param progress: What the environment reported.
    """
    if progress.warning:
        logger.warning(progress.message)
    else:
        logger.info(progress.message)


def _resolve_env_world(world: str | None,
                       port: int | None = None) -> tuple[EnvPaths, WorldState] | None:
    """
    Find the environment and the world to use inside it.

    With no world named, this follows :func:`~miney.env.manage.pick_world`: the world on
    the port that was asked for, the only world there is, or the only one that is
    running. A script therefore keeps working when a second world appears next to the
    one it uses, as long as that one is the one that is up.

    :param world: Explicitly requested world name, or None.
    :param port: Explicitly requested port, or None.
    :return: The environment and the world's state, or None if there is no environment.
    :raises MineyRunError: If no world matches, or if it cannot be told which is meant.
    """
    paths = find_env()
    if paths is None:
        return None

    states = list_states(paths)
    if world is not None:
        state = load_state(paths.state_file(world))
        if state is None:
            known = ", ".join(s.name for s in states) or "none"
            raise MineyRunError(
                f"No world named '{world}' in {paths.root}. Known worlds: {known}.\n"
                f"Create it with: uv run miney start --world {world}"
            )
        return paths, state

    if not states:
        raise MineyRunError(
            f"{paths.root} has no world yet. Create one with: uv run miney start"
        )

    chosen = manage.pick_world(paths, port=port)
    if chosen is not None:
        return paths, chosen

    # Ambiguous, and which kind of ambiguous decides what to suggest: with several
    # servers up, naming one is the only way out; with none up, starting one answers it
    # for every command afterwards.
    running = [state for state in states if manage.is_server_up(state)]
    suggestion = (running[0] if running else manage.last_used_world(paths) or states[0])
    if running:
        opening = "Several worlds are running, so Miney cannot tell which one you mean:"
        closing = ""
    else:
        opening = ("Several worlds exist and none of them is running, so Miney cannot "
                   "tell which one you mean:")
        closing = ("\nOr start one - everything after that follows the world that is "
                   f"up:\n    uv run miney start --world {suggestion.name}")
    raise MineyRunError(
        f"{opening}\n"
        f"{manage.describe_worlds(paths)}\n"
        f"Say which one:\n"
        f'    miney.Luanti(world="{suggestion.name}"){closing}'
    )


def _make_atexit_disconnect(luanti_ref: "weakref.ReferenceType[Luanti]") -> Callable[[], None]:
    """
    Build the handler that disconnects one :class:`Luanti` when the script ends.

    ``__del__`` cannot do this. Every namespace hanging off ``Luanti`` - ``Chat``,
    ``Nodes``, ``Lua``, ``Storage``, ``Callback`` - keeps a reference back to it, so the
    object is only ever reachable in a cycle and only the cyclic collector could free
    it. CPython does not promise to run that collector at interpreter shutdown, and in
    practice it does not: a script that ends without ``with`` never disconnected at all.
    The server then held the session until it timed out, and running the same script
    again a moment later was refused with *"Another client is already connected with
    this name."* - which reads like the user's own fault and is not.

    ``atexit`` runs while the interpreter is still whole, so the disconnect packet goes
    out and the name is free immediately.

    The handler holds a weak reference on purpose. ``atexit`` keeps whatever it is given
    alive until the process ends, and a strong reference here would keep the connection
    open for exactly as long as the bug it fixes did.

    :param luanti_ref: Weak reference to the object to disconnect.
    :return: The handler to hand to :func:`atexit.register`.
    """
    def _disconnect_at_exit() -> None:
        luanti = luanti_ref()
        if luanti is not None:
            luanti.disconnect()

    return _disconnect_at_exit


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
    """__init__([server, playername, password, port, invisible, world, autostart])
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
    :param int port: The apisocket port, defaults to 30000
    :param str world: Name of the world in the local ``.miney`` environment to connect to.
        Only needed when several exist. Ignored when an explicit ``server`` is given.
    :param bool autostart: Start the local Luanti server if it is not running, **and open a
        Luanti game window** connected to it. Ignored when an explicit server is given.
    """

    def __init__(self, server: str | None = None, playername: str | None = None,
                 password: str = "ChangeThePassword!", port: int | None = None,
                 invisible: bool = True, world: str | None = None, autostart: bool = True):
        """
        Connect to the Luanti server.

        If no ``server`` is given and this project has a local ``.miney`` environment
        (created by running ``uv run miney start`` once), Miney connects to that
        environment's world instead of guessing a host. Give an explicit ``server`` to
        bypass this entirely and connect to somebody else's server.

        When that world's server is not up, ``autostart`` starts it and then waits
        until it really accepts connections - a cold start generates the map and can
        take a while, so this prints one line saying what it is waiting for.

        **Autostart opens a Luanti window.** It does not only start a server process:
        it also launches the game client and logs it in, so a window appears on screen
        and stays there after your script has ended. That is the point - you watch your
        code change a world you are standing in - but it is worth knowing before you
        run a script from an editor, a notebook or a cron job. Pass ``autostart=False``
        to connect to an already running world and never launch anything.

        :param server: IP or DNS name of an Luanti server with installed miney mod
        :param port: The apisocket port, defaults to 30000
        :param invisible: If True, makes the Miney player invisible and grants creative privilege to be safe from mobs.
        :param world: Name of the world in the local ``.miney`` environment to connect to.
            Only needed when it cannot be worked out: with one world that one is used,
            and with several the one whose server is running - so a second world next to
            the one you work in changes nothing while it is shut down. Naming a ``port``
            picks the world on that port. Ignored when an explicit ``server`` is given.
        :param autostart: Start the local Luanti server if it is not running, and open a
            Luanti game window connected to it. Ignored when an explicit server is given.
        :raises MineyRunError: If the environment has no matching world, several worlds
            exist and none was named, or autostarting the world's server failed.
        """
        env_selection = None
        if server is None:
            env_selection = _resolve_env_world(world, port)

        if env_selection is not None:
            paths, state = env_selection
            if not manage.is_server_up(state):
                if not autostart:
                    raise MineyRunError(
                        f"The Luanti server for world '{state.name}' is not running.\n"
                        f"Start it first: uv run miney start --world {state.name}"
                    )
                # The only line Miney prints. Starting a world takes a while, and a
                # minute of silence looks like a hang to somebody in the REPL.
                print(
                    f"Starting the Luanti server for world '{state.name}' and opening "
                    "a Luanti window connected to it. The first start of a world "
                    "generates the map and can take a while."
                )
                state = manage.start(
                    paths, state.name, state.gameid, report=_log_progress
                ).state
            if port is None:
                port = state.port

        if server is None:
            server = "127.0.0.1"
        if port is None:
            port = 30000

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
                # Info, not warning: this is what every first connect looks like, and a
                # script that never configured logging would otherwise have logging's
                # last-resort handler print it to stderr as if something had gone wrong.
                logger.info(f"No account for '{self.playername}' yet. Registering one.")
                self.luanti.disconnect()  # Ensure clean state

                # Re-initialize and attempt to register
                self.luanti = LuantiClient(playername=self.playername, password=self.password, host=self.server,
                                                 port=self.port)
                try:
                    self.luanti.connect(register=True)
                    logger.info(f"Successfully registered and connected as '{self.playername}'.")
                    # Only true for a server reached over the network: the Miney mod
                    # lets a client on a local address run code without the privilege,
                    # which is every world "miney start" creates. "uv run miney check"
                    # reports the real answer for the server actually in use.
                    logger.info(
                        f"On a remote server '{self.playername}' also needs the 'miney' "
                        f"privilege: /grant {self.playername} miney"
                    )
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
        self._storage: Storage = Storage(self)
        self._assets: Assets = Assets(self)

        self._tools_cache = self.lua.run(
            """
            local node = {}
            for name, def in pairs(minetest.registered_tools) do
                table.insert(node, name)
            end return node
            """
        )
        self._tool = ToolIterable(self, self._tools_cache)

        # Registered once the connection really exists, so a failed connect leaves
        # nothing behind to run at exit.
        self._atexit_disconnect = _make_atexit_disconnect(weakref.ref(self))
        atexit.register(self._atexit_disconnect)

        # Without this, Miney's own player stays dead for the rest of the session: a
        # corpse standing in the world that answers every command with the position it
        # died at. See _get_up_again for why the client's own answer is not enough.
        self._invisible = invisible
        self._callbacks.register("player_dies", self._get_up_again,
                                 {"player_name": self.playername})

        # Optionally make player invisible and grant creative privilege
        if invisible:
            try:
                player_obj = self.players[self.playername]
                player_obj.invisible = True
                player_obj.creative = True
            except Exception as e:
                logger.error(f"Failed to set invisible/creative for player '{self.playername}': {e}")

    def _get_up_again(self, event) -> None:
        """
        Send Miney's own player back into the world after it died.

        Registered for every session, and never for anybody else's player - yours keeps
        the death screen it is supposed to get.

        The client does answer that screen by itself, but the answer is usually thrown
        away: the server only accepts a form it is still expecting, and the mod shows
        ``miney:code_form`` again for every command answer and every event - including
        the one that says the player just died. The server then logs *"submitted
        formspec ('__builtin:death') ... possible exploitation attempt"* and the player
        stays dead. Asking for the respawn from Lua goes through the channel that is
        always open anyway.

        Invisibility is put back on afterwards, because a game that gives players a skin
        gives them a fresh one when they respawn.

        :param event: The :class:`~miney.events.PlayerDiesEvent` that arrived.
        """
        try:
            self.lua.run(
                f"local player = minetest.get_player_by_name({self.lua.dumps(self.playername)})\n"
                f"if player then player:respawn() end"
            )
            if self._invisible:
                self.players[self.playername].invisible = True
        except Exception as error:  # noqa: BLE001 - a dead bot is not worth a traceback
            logger.error("Could not respawn '%s' after it died: %s", self.playername, error)

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
    def assets(self) -> 'Assets':
        """
        Pictures: the ones the game ships, and the ones you make yourself.

        See :class:`~miney.assets.Assets` for the whole picture.

        :Example:

            >>> lt.assets.textures.default.dirt
            'default_dirt.png'
            >>> lt.assets.upload(Path("cat.png"))
            'miney_3f9a1c7b2e04.png'

        :return: :class:`~miney.assets.Assets`
        """
        return self._assets

    @property
    def storage(self) -> 'Storage':
        """
        The world's key-value store, used like a dictionary.

        The one place that survives your script ending, and a server restart with it.
        See :class:`~miney.storage.Storage` for the whole picture.

        :Example:

            >>> lt.storage["home"] = "10,20,30"
            >>> lt.storage["home"]
            '10,20,30'

        :return: :class:`~miney.storage.Storage`
        """
        return self._storage

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
        See :class:`~miney.ToolIterable` for more details.

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
        # Nothing left for the interpreter to do at exit. Unregistering the instance's
        # own handler rather than the shared function keeps other open connections.
        handler = getattr(self, "_atexit_disconnect", None)
        if handler is not None:
            atexit.unregister(handler)
            self._atexit_disconnect = None

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
