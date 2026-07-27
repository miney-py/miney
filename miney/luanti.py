import atexit
import logging
import time
import weakref
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, Dict, Optional, Callable

from .assets import Assets
from .channel import Beacon, FileChannel, find_beacons
from .chat import Chat
from .events import Event
from .lua import Lua
from .callback import Callback
from .nodes import Nodes
from .player import PlayerIterable
from .storage import Storage
from .tool import ToolIterable
from .env import manage
from .env.paths import EnvPaths, find_env, syncing_service
from .env.state import WorldState, list_states, load_state
from .exceptions import MineyRunError


logger = logging.getLogger(__name__)


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


def _pick_beacons(world: str | None) -> list[Beacon]:
    """
    The channels of every Luanti server running on this computer, filtered by world.

    :param world: The world that was asked for, or None for all of them.
    :return: The matching beacons, most recently started first.
    :raises MineyRunError: If a world was named and no server is running it.
    """
    beacons = find_beacons()
    if world is None:
        return beacons
    matching = [one for one in beacons if one.world_name == world]
    if not matching and beacons:
        running = ", ".join(f"'{one.world_name}'" for one in beacons)
        raise MineyRunError(
            f"No Luanti server is running the world '{world}'. Running: {running}."
        )
    return matching


def _open_file_channel(world: str | None, port: int | None,
                       autostart: bool) -> FileChannel:
    """
    Attach to a Luanti server on this computer, starting one if that is wanted.

    Every server with the Miney mod leaves a beacon in Luanti's own ``mod_data``
    directory saying where its channel is, whoever started it - a world this project
    manages, or one the user opened from the Luanti menu. So this looks for a beacon
    first and only falls back to the project's own environment when nothing answers.

    :param world: The world to connect to, or None to work it out.
    :param port: The port of the world to start, if one has to be started.
    :param autostart: Whether starting a server is allowed.
    :return: The attached channel.
    :raises MineyRunError: If no server could be reached and none could be started.
    """
    candidates = _pick_beacons(world)
    if len(candidates) > 1:
        names = "\n".join(f"    {one.world_name}" for one in candidates)
        raise MineyRunError(
            f"Several Luanti servers are running, so Miney cannot tell which one you "
            f"mean:\n{names}\n"
            f'Say which one: miney.Luanti(world="{candidates[0].world_name}")'
        )

    for beacon in candidates:
        service = syncing_service(beacon.directory)
        if service:
            logger.warning(
                "This world's Miney channel is inside a folder that %s is syncing (%s). "
                "Every command is a file write, so expect the sync client to be busy.",
                service, beacon.directory,
            )
        try:
            return FileChannel(beacon.directory, timeout=5.0)
        except MineyRunError as error:
            # A beacon left behind by a server that was killed looks exactly like one
            # from a server that is up, and there is no process id in it to tell them
            # apart. So the only way to find out is to ask and see.
            logger.info("A server left its mark in %s but did not answer: %s",
                        beacon.directory, error)

    return _start_and_attach(world, port, autostart, tried=bool(candidates))


def _start_and_attach(world: str | None, port: int | None, autostart: bool,
                      tried: bool) -> FileChannel:
    """
    Start this project's world and attach to it once its mod is up.

    :param world: The world to start, or None to work it out.
    :param port: The port to prefer.
    :param autostart: Whether starting is allowed at all.
    :param tried: Whether a beacon was found and failed to answer, which changes what
        the error message should say.
    :return: The attached channel.
    :raises MineyRunError: If there is nothing to start, or it never came up.
    """
    selection = _resolve_env_world(world, port)
    if selection is None:
        if tried:
            raise MineyRunError(
                "A Luanti server left its mark on this computer but is not answering, "
                "and this project has no world of its own to start.\n"
                "Start Luanti again, or create a world here: uv run miney start"
            )
        raise MineyRunError(
            "No Luanti server with the Miney mod is running on this computer.\n"
            "Start one: uv run miney start\n"
            "Or open a world in Luanti yourself - Miney finds it either way, as long "
            "as the 'miney' mod is enabled for it."
        )

    paths, state = selection
    if manage.is_server_up(state) and not tried:
        raise MineyRunError(
            f"The server for world '{state.name}' is running, but it has no Miney "
            f"channel. That means its 'miney' mod is missing or too old.\n"
            f"Update it: uv run miney upgrade"
        )
    if not manage.is_server_up(state):
        if not autostart:
            raise MineyRunError(
                f"The Luanti server for world '{state.name}' is not running.\n"
                f"Start it first: uv run miney start --world {state.name}"
            )
        # The only line Miney prints. Starting a world takes a while, and a minute of
        # silence looks like a hang to somebody in the REPL.
        print(
            f"Starting the Luanti server for world '{state.name}' and opening "
            "a Luanti window connected to it. The first start of a world "
            "generates the map and can take a while."
        )
        state = manage.start(paths, state.name, state.gameid, report=_log_progress).state

    wanted = paths.world_dir(state.name).resolve()
    deadline = time.time() + 60
    while time.time() < deadline:
        for beacon in find_beacons(paths.luanti_dir):
            try:
                same = Path(beacon.world).resolve() == wanted
            except OSError:
                same = False
            if same:
                return FileChannel(beacon.directory, timeout=10.0)
        time.sleep(0.5)

    raise MineyRunError(
        f"The server for world '{state.name}' started, but its Miney mod never opened "
        f"a channel. Check the server log: {paths.log_file(state.name)}"
    )


def _make_atexit_disconnect(luanti_ref: "weakref.ReferenceType[Luanti]") -> Callable[[], None]:
    """
    Build the handler that disconnects one :class:`Luanti` when the script ends.

    ``__del__`` cannot do this. Every namespace hanging off ``Luanti`` - ``Chat``,
    ``Nodes``, ``Lua``, ``Storage``, ``Callback`` - keeps a reference back to it, so the
    object is only ever reachable in a cycle and only the cyclic collector could free
    it. CPython does not promise to run that collector at interpreter shutdown, and in
    practice it does not: a script that ends without ``with`` never disconnected at all.
    The server then held the session until it timed out, keeping its chat commands and
    its timers alive for half a minute after the script had gone.

    ``atexit`` runs while the interpreter is still whole, so the goodbye goes out, the
    last commands are flushed and the server cleans up straight away.

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
    """__init__([world, autostart, port])
    The Miney server object. Everything else hangs off it, and creating one connects.

    **It takes no arguments:**

    ::

        >>> lt = Luanti()

    Miney finds the Luanti server itself. It works for a world this project started and
    for one you opened in Luanti yourself, singleplayer included - the mod leaves a note
    saying where to reach it, and Miney reads that note. No account, no password, no
    port, and nobody joins your world.

    The one thing this cannot do is reach a Luanti on **another computer**: Miney talks
    to the mod through two files in Luanti's own directory, and a file on your disk is
    not on somebody else's machine.

    :param str world: Name of the world to connect to. Only needed when several servers
        are running at once; the error message lists them.
    :param bool autostart: Start this project's Luanti server if nothing is running,
        **and open a Luanti game window** connected to it.
    :param int port: Which world to start, by port, when more than one could be meant.
    """

    def __init__(self, world: str | None = None, autostart: bool = True,
                 port: int | None = None):
        """
        Connect to the Luanti server on this computer.

        Every server with the miney mod writes down where it can be reached, so this
        finds a world this project started and a world you opened from the Luanti menu
        equally well - including a singleplayer game, which no network client can reach
        at all.

        When nothing is running and this project has a ``.miney`` environment (created
        by ``uv run miney start`` once), ``autostart`` starts that world and then waits
        until its mod is up - a cold start generates the map and can take a while, so
        this prints one line saying what it is waiting for.

        **Autostart opens a Luanti window.** It does not only start a server process:
        it also launches the game client and logs it in, so a window appears on screen
        and stays there after your script has ended. That is the point - you watch your
        code change a world you are standing in - but it is worth knowing before you
        run a script from an editor, a notebook or a cron job. Pass ``autostart=False``
        to connect to an already running world and never launch anything.

        :param world: Which world to connect to, named by its directory. Only needed
            when several servers are running at once; the error message lists them.
        :param autostart: Start this project's Luanti server when nothing is running,
            and open a Luanti game window connected to it.
        :param port: Which world to start, by port, when more than one could be meant.
        :raises MineyRunError: If no server could be reached and none could be started,
            or if several are running and none was named.
        """
        #: The channel to the server: two append-only files in Luanti's own directory.
        self.transport = _open_file_channel(world, port, autostart)

        self._callbacks: Callback = Callback(self)

        # objects representing local properties
        self._lua: Lua = Lua(self.transport)
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
        self.lua.run(
            f'minetest.log("action", {self.lua.dumps(line)})', wait=False
        )

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
            self.lua.run("minetest.set_timeofday({})".format(value), wait=False)
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

        # Anything sent without waiting has to land before the connection goes. A script
        # whose last line is lt.nodes.set() would otherwise end, disconnect, and leave
        # the command unread in a file - the block never appears, and nothing says why.
        lua = getattr(self, "_lua", None)
        if lua is not None:
            try:
                lua.flush()
            except Exception as error:  # noqa: BLE001 - closing down, nowhere to raise
                logger.error("A command Miney had sent on failed: %s", error)

        # Best-effort cleanup of registered callbacks before dropping the connection
        if hasattr(self, "_callbacks") and self._callbacks:
            try:
                self._callbacks.shutdown()
            except Exception as e:
                logger.error(f"Error during callback shutdown: {e}")

        transport = getattr(self, "transport", None)
        if transport is not None:
            transport.close()

    def __del__(self) -> None:
        """
        Destructor for Luanti.

        .. note::
            Using a 'with' statement is the recommended way to ensure
            a clean disconnection, as calling disconnect during interpreter
            shutdown is not reliable.
        """
        transport = getattr(self, "transport", None)
        if transport is not None:
            transport.close()

    def __repr__(self):
        return '<Luanti server "{}">'.format(self.transport.directory.name)
