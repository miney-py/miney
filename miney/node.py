from miney import Point
from collections.abc import MutableMapping
from typing import Union, TYPE_CHECKING
from math import floor
from .inventory import Inventory
from .point import Point
from .storage import _MetaStore
if TYPE_CHECKING:
    from .luanti import Luanti


class Node(Point):
    def __init__(self, x: Union[int, float] = 0, y: Union[int, float] = 0, z: Union[int, float] = 0,
                 name: str = "default:dirt", param1: int = None, param2: int = None, luanti: 'Luanti' = None):
        super().__init__(floor(x), floor(y), floor(z))
        self.name = name
        self.param1 = param1
        self.param2 = param2
        self._luanti = luanti
        self._inventory = None
        self._meta = None

    @property
    def inventory(self) -> Inventory:
        """
        Get the inventory of this node, if it has one.

        >>> chest_inventory = lt.nodes.get(Point(0, 0, 0)).inventory.add(lt.tool.default.dirt, 100)

        :return: The inventory object for this node.
        :raises: AttributeError if the node is not bound to a Luanti instance.
        """
        if self._luanti is None:
            raise AttributeError("Node is not bound to a Luanti instance and cannot access inventory.")
        if self._inventory is None:
            self._inventory = Inventory(self._luanti, self)
        return self._inventory

    @property
    def meta(self) -> MutableMapping[str, str]:
        """
        What Luanti stored on this block, used like a dictionary.

        Every block can carry a little table of text, and the game is what fills it: a
        sign's ``"text"``, the ``"infotext"`` shown when you point at something, a
        furnace's fuel. This is that table, and it reads and writes like a ``dict``::

            >>> sign = lt.nodes.get(Point(0, 10, 0))
            >>> sign.meta["text"] = "This way"
            >>> dict(sign.meta)
            {'text': 'This way', 'infotext': '"This way"'}

        Keys and values are strings, both of them - the same rule as
        :attr:`lt.storage <miney.Luanti.storage>`, and for the same reason: Luanti
        writes text and nothing else.

        Which keys a block has is up to the game, not to Miney. Read the whole table
        first to find out what is there::

            >>> for key, value in lt.nodes.get(point).meta.items():
            ...     print(key, "=", value)

        .. warning::

           These keys belong to the **game**, not to you. Writing nonsense into a
           chest's ``"inventory"`` breaks that chest, and ``clear()`` empties the
           block's own metadata rather than some corner of it.
           :attr:`player.storage <miney.Player.storage>` is the store that is safely
           yours; this one is the block's.

        :return: The block's metadata, as a mutable mapping.
        :raises AttributeError: If the node is not bound to a Luanti instance.
        """
        if self._luanti is None:
            raise AttributeError(
                "Node is not bound to a Luanti instance and cannot access meta. "
                "Read the block from the world first: lt.nodes.get(Point(0, 10, 0))."
            )
        if self._meta is None:
            position = self._luanti.lua.dumps({"x": self.x, "y": self.y, "z": self.z})
            # get_meta answers nil for a block the server does not hold in memory, and a
            # nil MetaDataRef writes nowhere and reads back empty - without a word. The
            # mapblock is loaded first for the same reason nodes.set() does it.
            self._meta = _MetaStore(
                self._luanti,
                f"(function() local p = {position} "
                f"minetest.load_area(p) return minetest.get_meta(p) end)()",
                f"Luanti Node meta ({self.x}, {self.y}, {self.z})",
                "lt.nodes.get(point).meta",
            )
        return self._meta

    @property
    def position(self) -> Point:
        """
        Returns the position of the node as a Point object.
        Since a Node is a subclass of Point, it returns itself.

        :return: A Point object representing the node's coordinates.
        """
        return self

    def __repr__(self):
        return f"<Luanti Node(x={self.x}, y={self.y}, z={self.z}, name={self.name})>"
