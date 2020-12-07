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

    def __len__(self):
        return int(self.length())

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

    def length(self):
        return sqrt((self.x * self.x) + (self.y * self.y) + (self.z * self.z))

    def normalize(self):
        return Vector((self.x / self.length()), (self.y / self.length()), (self.z / self.length()))


def angle(a, b):
    m = a.x * b.x + a.y * b.y + a.z * b.z
    return degrees(acos(m / (a.length() * b.length())))


def horizontal_angle(a, b):
    return angle(Vector(a.x, a.y, 0), Vector(b.x, b.y, 0))


def vertical_angle(a, b):
    return angle(Vector(0, a.y, a.z), Vector(0, b.y, b.z))
