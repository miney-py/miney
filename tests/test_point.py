from __future__ import annotations
import math
import pytest
from miney.point import Point


def test_distance_and_center():
    a = Point(0, 0, 0)
    b = Point(3, 4, 0)
    dist = a.distance(b)
    center = a.center(b)
    assert math.isclose(dist, 5.0)
    assert center.x == pytest.approx(1.5)
    assert center.y == pytest.approx(2.0)
    assert center.z == pytest.approx(0.0)


def test_add_sub_mul_div_and_len_getitem_iter():
    a = Point(1, 2, 3)
    b = Point(4, 5, 6)

    c = a + b
    d = b - a
    e = a * 2
    f = b / 2

    assert (c.x, c.y, c.z) == (5, 7, 9)
    assert (d.x, d.y, d.z) == (3, 3, 3)
    assert (e.x, e.y, e.z) == (2, 4, 6)
    assert (f.x, f.y, f.z) == (2, 2.5, 3)

    assert len(a) == 3
    assert a[0] == 1 and a[1] == 2 and a[2] == 3
    assert dict(a) == {"x": 1, "y": 2, "z": 3}


def test_length_and_normalize_and_angle():
    a = Point(0, 3, 4)
    assert a.length() == pytest.approx(5.0)

    n = a.normalize()
    assert n.length() == pytest.approx(1.0)

    b = Point(0, 1, 0)
    angle_deg = a.angle(b)
    assert angle_deg == pytest.approx(53.130102, rel=1e-6)
