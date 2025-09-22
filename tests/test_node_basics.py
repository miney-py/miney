from __future__ import annotations
import pytest
from miney.node import Node
from miney.point import Point


def test_node_is_point_and_coords_and_repr():
    n = Node(1, 2, 3)
    assert isinstance(n, Point)
    assert (n.x, n.y, n.z) == (1, 2, 3)

    s = repr(n)
    assert "1" in s and "2" in s and "3" in s

    m = n + Point(1, 1, 1)
    assert (m.x, m.y, m.z) == (2, 3, 4)

    assert len(n) == 3
    with pytest.raises(ZeroDivisionError):
        _ = Node(0, 0, 0).normalize()
