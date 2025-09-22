from __future__ import annotations
import pytest
from miney.vector import Vector, angle, horizontal_angle, vertical_angle


def test_basic_ops_and_len_getitem_iter():
    a = Vector(1, 2, 3)
    b = Vector(4, 5, 6)

    c = a + b
    d = b - a
    dot = a * b

    assert (c.x, c.y, c.z) == (5, 7, 9)
    assert (d.x, d.y, d.z) == (3, 3, 3)
    assert dot == 32

    assert len(a) == 3
    assert a[0] == 1 and a[1] == 2 and a[2] == 3
    assert dict(a) == {"x": 1, "y": 2, "z": 3}


def test_length_normalize_and_angles():
    v = Vector(0, 3, 4)
    assert v.length() == pytest.approx(5.0)

    n = v.normalize()
    assert n.length() == pytest.approx(1.0)

    a = Vector(1, 0, 0)
    b = Vector(0, 1, 0)
    assert angle(a, b) == pytest.approx(90.0)
    assert horizontal_angle(a, b) == pytest.approx(90.0)
    assert vertical_angle(a, b) == pytest.approx(0.0)
