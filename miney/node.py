from miney import Point
from typing import Union
from math import floor


class Node(Point):
    def __init__(self, x: Union[int, float] = 0, y: Union[int, float] = 0, z: Union[int, float] = 0,
                 name: str = "default:dirt", param1: int = None, param2: int = None):
        self.x = floor(x)
        self.y = floor(y)
        self.z = floor(z)
        self.name = name
        self.param1 = param1
        self.param2 = param2

    def __repr__(self):
        return f"<minetest Node(x={self.x}, y={self.y}, z={self.z}, name={self.name})>"
