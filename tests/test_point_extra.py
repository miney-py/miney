from __future__ import annotations
import pytest
from miney.point import Point


def test_getitem_errors_and_string_access():
    p = Point(1, 2, 3)
    assert p["x"] == 1
    with pytest.raises(IndexError):
        _ = p[3]
    with pytest.raises(AttributeError):
        _ = p["does_not_exist"]


def test_inplace_ops_and_neg():
    p = Point(1, 2, 3)
    q = Point(2, 3, 4)
    p += q
    assert (p.x, p.y, p.z) == (3, 5, 7)
    p -= Point(1, 1, 1)
    assert (p.x, p.y, p.z) == (2, 4, 6)
    n = -p
    assert (n.x, n.y, n.z) == (-2, -4, -6)


def test_mul_div_not_implemented_with_wrong_type():
    p = Point(1, 2, 3)
    assert p.__mul__("x") is NotImplemented
    assert p.__truediv__("x") is NotImplemented


def test_normalize_and_angle_zero_length_raises():
    p0 = Point(0, 0, 0)
    with pytest.raises(ZeroDivisionError):
        _ = p0.normalize()
    with pytest.raises(ZeroDivisionError):
        _ = p0.angle(Point(1, 0, 0))


def test_repr_includes_coordinates():
    s = repr(Point(7, 8, 9))
    assert "Luanti Point" in s
    assert "7" in s and "8" in s and "9" in s
