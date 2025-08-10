from miney import Point
from typing import Union, TYPE_CHECKING
from math import floor
from .inventory import Inventory
from .point import Point
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

    @property
    def inventory(self) -> Inventory:
        """
        Get the inventory of this node, if it has one.

        :return: The inventory object for this node.
        :raises: AttributeError if the node is not bound to a Luanti instance.
        """
        if self._luanti is None:
            raise AttributeError("Node is not bound to a Luanti instance and cannot access inventory.")
        if self._inventory is None:
            self._inventory = Inventory(self._luanti, self)
        return self._inventory

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
