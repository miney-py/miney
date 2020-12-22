from typing import Union
from math import sqrt, acos, degrees


class Point:

    def __init__(self, x: Union[int, float] = 0, y: Union[int, float] = 0, z: Union[int, float] = 0):
        print("point")
        self.x = x
        self.y = y
        self.z = z

    def distance(self, b: "Point") -> float:
        return sqrt((b.x - self.x) ** 2 + (b.y - self.y) ** 2 + (b.z - self.z) ** 2)

    def center(self, b: "Point") -> "Point":
        return Point((b.x - self.x) / 2, (b.y - self.y) / 2, (b.z - self.z) / 2)
    
    def dict(self) -> dict:
        return self.__dict__

    def __add__(self, other: "Point") -> "Point":
        return Point(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Point") -> "Point":
        return Point(self.x - other.x, self.y - other.y, self.z - other.z)

    def __iadd__(self, o):
        self.x += o.x
        self.y += o.y
        self.z += o.z
        return self

    def __isub__(self, o):
        self.x -= o.x
        self.y -= o.y
        self.z -= o.z
        return self

    def __neg__(self):
        return Point(-self.x, -self.y, -self.z)

    def length(self) -> float:
        """
        Returns the distance to the x=0, y=0, z=0 point.
        :return:
        :rtype:
        """
        return sqrt((self.x * self.x) + (self.y * self.y) + (self.z * self.z))

    def normalize(self):
        return Point((self.x / self.length()), (self.y / self.length()), (self.z / self.length()))

    def angle(self, b):
        m = self.x * b.x + self.y * b.y + self.z * b.z
        return degrees(acos(m / (self.length() * b.length())))

    def __repr__(self):
        return f"<minetest Point(x={self.x}, y={self.y}, z={self.z})>"
