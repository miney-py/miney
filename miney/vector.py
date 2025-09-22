# https://github.com/kirill-belousov/vector3d/blob/master/vector3d/point.py
from math import sqrt, acos, degrees


class Vector:
    x = float()
    y = float()
    z = float()

    def __init__(self, x: float = 0, y: float = 0, z: float = 0):
        self.x = x
        self.y = y
        self.z = z

    def __eq__(self, other):
        if self.x == other.x and self.y == other.y and self.z == other.z:
            return True
        else:
            return False

    def __len__(self) -> int:
        """
        Return the number of coordinates, which is always 3.
        Allows conversion to list or tuple.
        """
        return 3

    def __getitem__(self, item_key: int):
        """
        Get a coordinate by its index (0=x, 1=y, 2=z).
        """
        if item_key == 0:
            return self.x
        elif item_key == 1:
            return self.y
        elif item_key == 2:
            return self.z
        else:
            raise IndexError("Vector index out of range")

    def __add__(self, o):
        return Vector((self.x + o.x), (self.y + o.y), (self.z + o.z))

    def __sub__(self, o):
        return Vector((self.x - o.x), (self.y - o.y), (self.z - o.z))

    def __mul__(self, o):
        return (self.x * o.x) + (self.y * o.y) + (self.z * o.z)

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
        return Vector(-self.x, -self.y, -self.z)

    def __iter__(self):
        """
        Allow the vector to be converted to a dict.
        """
        yield 'x', self.x
        yield 'y', self.y
        yield 'z', self.z

    def length(self):
        return sqrt((self.x * self.x) + (self.y * self.y) + (self.z * self.z))

    def normalize(self):
        return Vector((self.x / self.length()), (self.y / self.length()), (self.z / self.length()))


def angle(a, b) -> float:
    """
    Compute the angle (in degrees) between vectors a and b.
    Returns 0.0 if either vector has zero length.
    Clamps cosine to [-1, 1] for numeric stability.
    """
    la = a.length()
    lb = b.length()
    if la == 0 or lb == 0:
        return 0.0
    cos_theta = (a.x * b.x + a.y * b.y + a.z * b.z) / (la * lb)
    if cos_theta > 1.0:
        cos_theta = 1.0
    elif cos_theta < -1.0:
        cos_theta = -1.0
    return degrees(acos(cos_theta))


def horizontal_angle(a, b):
    return angle(Vector(a.x, a.y, 0), Vector(b.x, b.y, 0))


def vertical_angle(a, b):
    return angle(Vector(0, a.y, a.z), Vector(0, b.y, b.z))
