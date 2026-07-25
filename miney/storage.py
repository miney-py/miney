"""
A place on the server where a script can leave something for the next run.
"""
from collections.abc import ItemsView, Iterator, KeysView, MutableMapping, ValuesView
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .luanti import Luanti


logger = logging.getLogger(__name__)


class Storage(MutableMapping):
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
    own data.

    You do not create this class yourself, it is reached through
    :attr:`~miney.Luanti.storage`.
    """

    def __init__(self, luanti: "Luanti"):
        """
        :param luanti: The parent :class:`~miney.Luanti` object.
        """
        self.lt = luanti

    def __repr__(self) -> str:
        fields = self._fields()
        if len(fields) > 5:
            return f"<Luanti Storage: {len(fields)} keys>"
        return f"<Luanti Storage: {fields!r}>"

    def _fields(self) -> dict[str, str]:
        """
        The whole store, in one call.

        Read through ``to_table()`` rather than ``get_string()`` on purpose: Luanti
        still supports a deprecated ``${key}`` syntax, and ``get_string("${home}")``
        returns the value of *home* instead of the text that was stored. ``to_table()``
        hands out what was actually written.

        :return: Every key and value. Empty while nothing is stored.
        """
        fields = self.lt.lua.run("return storage:to_table().fields")
        # An empty store serializes as nil, not as an empty table.
        return fields or {}

    @staticmethod
    def _check_key(key: str) -> str:
        """
        :param key: The key to validate.
        :return: The key, unchanged.
        :raises TypeError: If the key is not a string.
        :raises ValueError: If the key is empty.
        """
        if not isinstance(key, str):
            raise TypeError(
                f"Storage keys are strings, not {type(key).__name__}. "
                f'Use lt.storage[str({key!r})] if you meant the text.'
            )
        if not key:
            raise ValueError("Storage keys cannot be empty.")
        return key

    def __getitem__(self, key: str) -> str:
        """
        :param key: The key to look up.
        :return: The stored text.
        :raises KeyError: If the key is not in the store.
        """
        value = self._fields().get(self._check_key(key))
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
        self._check_key(key)
        if not isinstance(value, str):
            raise TypeError(
                f"Storage values are strings, not {type(value).__name__}. "
                f"Use str({value!r}) for a single value, or json.dumps({value!r}) "
                f"for a list or a dictionary."
            )
        if not value:
            raise ValueError(
                "Storage cannot hold an empty string: Luanti deletes a key when it is "
                f'set to "". Use "del lt.storage[{key!r}]" if that is what you mean.'
            )
        self.lt.lua.run(
            f"storage:set_string({self.lt.lua.dumps(key)}, {self.lt.lua.dumps(value)}) "
            f"return true"
        )

    def __delitem__(self, key: str) -> None:
        """
        :param key: The key to remove.
        :raises KeyError: If the key is not in the store.
        """
        self._check_key(key)
        removed = self.lt.lua.run(
            f"local key = {self.lt.lua.dumps(key)} "
            f"if not storage:contains(key) then return false end "
            f"storage:set_string(key, '') "
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
        Remove everything from the store.

        Affects every script using this world, not only yours.
        """
        self.lt.lua.run("storage:from_table(nil) return true")
        logger.info("Cleared the world storage.")
