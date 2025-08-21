from typing import Union
from math import sqrt, acos, degrees


class Point:
    """
    A point is a position inside a three dimensional system.
    """
    def __init__(self, x: Union[int, float] = 0, y: Union[int, float] = 0, z: Union[int, float] = 0):
        self.x = x
        self.y = y
        self.z = z

    def distance(self, b: "Point") -> float:
        """
        Measure the distance between this point and Point b.

        :param b: Another Point
        :return: Distance
        """
        return sqrt((b.x - self.x) ** 2 + (b.y - self.y) ** 2 + (b.z - self.z) ** 2)

    def center(self, b: "Point") -> "Point":
        """
        Get the exact point in the center between this point and point b.

        :param b: Another Point
        :return: The center point
        """
        return (self + b) / 2

    def __add__(self, other: "Point") -> "Point":
        return Point(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Point") -> "Point":
        return Point(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: Union[int, float]) -> "Point":
        if not isinstance(scalar, (int, float)):
            return NotImplemented
        return Point(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: Union[int, float]) -> "Point":
        return self.__mul__(scalar)

    def __truediv__(self, scalar: Union[int, float]) -> "Point":
        if not isinstance(scalar, (int, float)):
            return NotImplemented
        return Point(self.x / scalar, self.y / scalar, self.z / scalar)

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

    def __len__(self) -> int:
        """
        Return the number of coordinates, which is always 3.
        Allows conversion to list or tuple.
        """
        return 3

    def __iter__(self):
        """
        Allow the point to be converted to a dict.
        """
        yield 'x', self.x
        yield 'y', self.y
        yield 'z', self.z

    def __getitem__(self, item_key: Union[int, str]):
        """
        Allow accessing coordinates by index (0=x, 1=y, 2=z) or attribute name.
        """
        if isinstance(item_key, int):
            if item_key == 0:
                return self.x
            elif item_key == 1:
                return self.y
            elif item_key == 2:
                return self.z
            else:
                raise IndexError("Point index out of range")
        # Fallback to original behavior for string keys
        return self.__getattribute__(item_key)

    def __repr__(self):
        return f"<Luanti Point(x={self.x}, y={self.y}, z={self.z})>"
