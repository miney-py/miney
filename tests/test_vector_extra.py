from __future__ import annotations
import pytest
from miney.vector import Vector, angle


def test_zero_length_angle_returns_zero():
    a = Vector(0, 0, 0)
    b = Vector(1, 0, 0)
    assert angle(a, b) == pytest.approx(0.0)


def test_iadd_isub_and_neg():
    v = Vector(1, 2, 3)
    v += Vector(1, 1, 1)
    assert (v.x, v.y, v.z) == (2, 3, 4)
    v -= Vector(2, 0, 1)
    assert (v.x, v.y, v.z) == (0, 3, 3)
    n = -v
    assert (n.x, n.y, n.z) == (0, -3, -3)


def test_vector_equality():
    assert Vector(1, 2, 3) == Vector(1, 2, 3)
    assert Vector(1, 2, 3) != Vector(1, 2, 4)
