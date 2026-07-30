"""
Places on the server where a script can leave something for the next run.
"""
from collections.abc import ItemsView, Iterator, KeysView, MutableMapping, ValuesView
import logging
from typing import TYPE_CHECKING

from .exceptions import PlayerOffline

if TYPE_CHECKING:
    from .luanti import Luanti
    from .player import Player


logger = logging.getLogger(__name__)

#: What the Lua side answers when the thing holding the store is not there. A byte no
#: stored text can contain, so it can never be mistaken for a value somebody wrote.
_ABSENT = "\0absent"


class _MetaStore(MutableMapping):
    """
    One of Luanti's ``MetaDataRef`` tables, used like a dictionary.

    Not a class you use directly. :class:`Storage` is the world's store and
    :class:`PlayerStorage` is one player's, and both are reached through a property.

    The two differ in three things, which is why this exists once instead of twice: the
    Lua expression that finds the store, whether that expression can come back empty
    (a player who left), and whether the keys carry a prefix that hides everything the
    store also holds for somebody else.
    """

    def __init__(
        self,
        luanti: "Luanti",
        ref: str,
        label: str,
        how: str,
        prefix: str = "",
        absent: str = "",
    ):
        """
        :param luanti: The parent :class:`~miney.Luanti` object.
        :param ref: Lua expression giving the ``MetaDataRef``, evaluated on every call.
        :param label: How this store names itself in a ``repr``.
        :param how: How the user writes this store in their code, for error messages.
        :param prefix: Put in front of every key on the way in, taken off on the way out
                       and used to hide keys that are not ours. Empty for a store that is
                       entirely Miney's already.
        :param absent: The message for :class:`~miney.PlayerOffline` when ``ref`` finds
                       nothing. Empty when it always finds something.
        """
        self.lt = luanti
        self._ref = ref
        self._label = label
        self._how = how
        self._prefix = prefix
        self._absent = absent

    def __repr__(self) -> str:
        fields = self._fields()
        if len(fields) > 5:
            return f"<{self._label}: {len(fields)} keys>"
        return f"<{self._label}: {fields!r}>"

    def _run(self, body: str, wait: bool = True):
        """
        Run ``body`` with the store bound to the Lua name ``meta``.

        :param body: Lua, using ``meta``.
        :param wait: Whether to wait for the answer.
        :return: What the Lua returned.
        :raises miney.PlayerOffline: If the store is not there anymore.
        """
        answer = self.lt.lua.run(
            f"local meta = {self._ref} "
            f"if not meta then return {self.lt.lua.dumps(_ABSENT)} end "
            f"{body}",
            wait=wait,
        )
        if answer == _ABSENT:
            raise PlayerOffline(self._absent)
        return answer

    def _fields(self) -> dict[str, str]:
        """
        The whole store, in one call.

        Read through ``to_table()`` rather than ``get_string()`` on purpose: Luanti
        still supports a deprecated ``${key}`` syntax, and ``get_string("${home}")``
        returns the value of *home* instead of the text that was stored. ``to_table()``
        hands out what was actually written.

        :return: Every key and value that belongs to this store. Empty while nothing is
                 stored.
        """
        # An empty store serializes as nil, not as an empty table.
        fields = self._run("return meta:to_table().fields") or {}
        if not self._prefix:
            return fields
        cut = len(self._prefix)
        return {key[cut:]: value
                for key, value in fields.items() if key.startswith(self._prefix)}

    def _check_key(self, key: str) -> str:
        """
        :param key: The key to validate.
        :return: The key with the store's prefix in front of it.
        :raises TypeError: If the key is not a string.
        :raises ValueError: If the key is empty.
        """
        if not isinstance(key, str):
            raise TypeError(
                f"Storage keys are strings, not {type(key).__name__}. "
                f"Use {self._how}[str({key!r})] if you meant the text."
            )
        if not key:
            raise ValueError("Storage keys cannot be empty.")
        return self._prefix + key

    def __getitem__(self, key: str) -> str:
        """
        :param key: The key to look up.
        :return: The stored text.
        :raises KeyError: If the key is not in the store.
        """
        self._check_key(key)
        value = self._fields().get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: str) -> None:
        """
        :param key: The key to store under.
        :param value: The text to store.
        :raises TypeError: If the key or the value is not a string.
        :raises ValueError: If the key or the value is empty.
        """
        stored_key = self._check_key(key)
        if not isinstance(value, str):
            raise TypeError(
                f"Storage values are strings, not {type(value).__name__}. "
                f"Use str({value!r}) for a single value, or json.dumps({value!r}) "
                f"for a list or a dictionary."
            )
        if not value:
            raise ValueError(
                "Storage cannot hold an empty string: Luanti deletes a key when it is "
                f'set to "". Use "del {self._how}[{key!r}]" if that is what you mean.'
            )
        # A store that cannot go away is written without waiting, so a loop of writes
        # costs one server step instead of one each. A player's store waits: there the
        # write can fail by the player leaving, and a failure nobody hears about is how
        # a script ends up believing it saved something.
        self._run(
            f"meta:set_string({self.lt.lua.dumps(stored_key)}, "
            f"{self.lt.lua.dumps(value)})",
            wait=bool(self._absent),
        )

    def __delitem__(self, key: str) -> None:
        """
        :param key: The key to remove.
        :raises KeyError: If the key is not in the store.
        """
        stored_key = self._check_key(key)
        removed = self._run(
            f"local key = {self.lt.lua.dumps(stored_key)} "
            f"if not meta:contains(key) then return false end "
            f"meta:set_string(key, '') "
            f"return true"
        )
        if not removed:
            raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        """
        :return: An iterator over the keys.
        """
        return iter(self._fields())

    def __len__(self) -> int:
        """
        :return: How many keys are stored.
        """
        return len(self._fields())

    def keys(self) -> KeysView[str]:
        """
        :return: All keys, read in a single call to the server.
        """
        return self._fields().keys()

    def values(self) -> ValuesView[str]:
        """
        :return: All values, read in a single call to the server.
        """
        return self._fields().values()

    def items(self) -> ItemsView[str, str]:
        """
        :return: All key-value pairs, read in a single call to the server.
        """
        return self._fields().items()

    def clear(self) -> None:
        """
        Remove everything from this store.
        """
        if self._prefix:
            # Everything under the prefix, and nothing else - the table this sits in
            # belongs to the game as well, and from_table(nil) would take that with it.
            keys = [self._prefix + key for key in self._fields()]
            if keys:
                self._run(
                    f"for _, key in ipairs({self.lt.lua.dumps(keys)}) do "
                    f"meta:set_string(key, '') end return true"
                )
        else:
            self._run("meta:from_table(nil) return true")
        logger.info("Cleared %s.", self._label)


class Storage(_MetaStore):
    """
    The world's key-value store, used like a dictionary.

    Everything a script does is gone when it ends: variables live in Python, and even
    the Lua names from :meth:`~miney.Lua.run` disappear with the connection. This is
    the exception. What you put here is written into the world and is still there for
    the next run, and after a server restart::

        >>> lt.storage["home"] = "10,20,30"
        >>> lt.storage["home"]
        '10,20,30'

    It behaves like a ``dict`` - ``in``, ``len()``, ``for``, ``.get()``, ``.pop()``,
    ``.update()`` and ``del`` all work::

        >>> "home" in lt.storage
        True
        >>> for key, value in lt.storage.items():
        ...     print(key, value)
        home 10,20,30
        >>> del lt.storage["home"]

    **Keys and values are strings, both of them.** Luanti writes text and nothing else -
    its ``set_int`` and ``set_float`` only convert to text on the way in, and what comes
    back out is a string either way. So Miney does not pretend otherwise: assigning a
    number raises a :class:`TypeError` instead of silently handing back ``"7"`` where you
    wrote ``7``. Convert on the way in and out::

        >>> lt.storage["visits"] = str(41 + 1)
        >>> int(lt.storage["visits"])
        42

    For anything with a shape, use :mod:`json`::

        >>> import json
        >>> lt.storage["seen"] = json.dumps({"players": ["Steve", "Alex"]})
        >>> json.loads(lt.storage["seen"])["players"]
        ['Steve', 'Alex']

    There is one store per world, not one per player, and it is not private: every
    Miney script connecting to that world reads and writes the same keys. Prefix what
    belongs to one project. No other mod on the server sees them though - Luanti files
    every key under the mod that wrote it, so nothing here can collide with a game's
    own data. :attr:`player.storage <miney.Player.storage>` is the same thing for one
    player.

    You do not create this class yourself, it is reached through
    :attr:`~miney.Luanti.storage`.
    """

    def __init__(self, luanti: "Luanti"):
        """
        :param luanti: The parent :class:`~miney.Luanti` object.
        """
        super().__init__(luanti, "storage", "Luanti Storage", "lt.storage")


class PlayerStorage(_MetaStore):
    """
    One player's key-value store, used like a dictionary.

    The same idea as :attr:`lt.storage <miney.Luanti.storage>`, except that every player
    has their own. What you write here is stored with that player and is still there
    after they log out, and after a server restart::

        >>> player = lt.players["Steve"]
        >>> player.storage["home"] = "10,20,30"
        >>> player.storage["home"]
        '10,20,30'

    It behaves like a ``dict``, and like the world store it holds **strings only** - use
    :class:`str` on the way in and :class:`int` or :mod:`json` on the way out::

        >>> player.storage["deaths"] = str(int(player.storage.get("deaths", "0")) + 1)
        >>> lt.chat.send_to_player(player.name, f"You died {player.storage['deaths']} times.")

    Use it for what belongs to one person - where they set their home, how far they got,
    what they answered last time - and :attr:`lt.storage <miney.Luanti.storage>` for what
    belongs to the world.

    .. note::
        Luanti keeps this in the same place a game keeps its own notes about the player,
        so Miney puts your keys in a corner of their own. Yours are the only ones you
        see, the only ones you can delete, and nothing you write can break the game's
        idea of that player. The names have a prefix on the Lua side that you never type
        and never see.

    You do not create this class yourself, it is reached through
    :attr:`player.storage <miney.Player.storage>`.
    """

    #: Written in front of every key inside Luanti, so a game's own notes about the
    #: player and Miney's own (the record :meth:`~miney.Player.hold` leaves, the
    #: appearance :attr:`~miney.Player.invisible` puts aside) stay out of reach.
    PREFIX = "miney:data:"

    def __init__(self, player: "Player"):
        """
        :param player: The :class:`~miney.Player` this store belongs to.
        """
        name = player.lt.lua.dumps(player.name)
        super().__init__(
            player.lt,
            f"minetest.get_player_by_name({name}) and "
            f"minetest.get_player_by_name({name}):get_meta()",
            f'Player "{player.name}" storage',
            "player.storage",
            prefix=self.PREFIX,
            absent=f"There is no player {player.name!r} in the game, so there is "
                   f"nothing to store for them.",
        )
