"""The packed form nodes.get() reads a region back in.

The coordinates are not transmitted - they are rebuilt by walking the region in the
same order the server walked it. Getting that walk wrong would put the right nodes at
the wrong places, which is the kind of bug that looks like the world moved.
"""
from __future__ import annotations
import pytest

from miney.exceptions import DataError
from miney.node import Node
from miney.nodes import Nodes, _decode_nodes
from miney.point import Point


def _encode(names_by_position, corner1, corner2):
    """Build the packed form the mod produces, so a decode can be checked against it."""
    x1, y1, z1 = corner1
    x2, y2, z2 = corner2
    palette, index_of, runs = [], {}, []
    last, run = None, 0
    for x in range(x1, x2 + 1):
        for y in range(y1, y2 + 1):
            for z in range(z1, z2 + 1):
                name, p1, p2 = names_by_position(x, y, z)
                if name not in index_of:
                    palette.append(name)
                    index_of[name] = len(palette)
                token = f"{index_of[name]},{p1},{p2}"
                if token == last:
                    run += 1
                else:
                    if last:
                        runs.append(f"{last}x{run}")
                    last, run = token, 1
    if last:
        runs.append(f"{last}x{run}")
    return " ".join(palette) + "|" + " ".join(runs)


def test_positions_come_back_in_x_outer_z_inner_order():
    """The order nodes.get() has always returned. Scripts index into this list."""
    corner1, corner2 = (0, 0, 0), (1, 1, 1)
    packed = _encode(lambda x, y, z: (f"m:n{x}{y}{z}", 0, 0), corner1, corner2)

    nodes = _decode_nodes(packed, corner1, corner2, luanti=None)

    assert [(n.x, n.y, n.z) for n in nodes] == [
        (0, 0, 0), (0, 0, 1), (0, 1, 0), (0, 1, 1),
        (1, 0, 0), (1, 0, 1), (1, 1, 0), (1, 1, 1),
    ]


def test_a_run_that_crosses_row_and_layer_boundaries():
    """One long run has to be unpacked across the z, y and x wraps."""
    corner1, corner2 = (0, 0, 0), (2, 2, 2)
    packed = "mcl_core:stone|1,0,0x27"

    nodes = _decode_nodes(packed, corner1, corner2, luanti=None)

    assert len(nodes) == 27
    assert all(n.name == "mcl_core:stone" for n in nodes)
    assert (nodes[0].x, nodes[0].y, nodes[0].z) == (0, 0, 0)
    assert (nodes[13].x, nodes[13].y, nodes[13].z) == (1, 1, 1)
    assert (nodes[-1].x, nodes[-1].y, nodes[-1].z) == (2, 2, 2)


def test_params_and_several_names_survive():
    corner1, corner2 = (5, -3, 7), (6, -3, 7)
    packed = "air mcl_core:tree|1,15,0x1 2,4,13x1"

    a, b = _decode_nodes(packed, corner1, corner2, luanti=None)

    assert (a.name, a.param1, a.param2) == ("air", 15, 0)
    assert (b.name, b.param1, b.param2) == ("mcl_core:tree", 4, 13)
    assert (a.x, a.y, a.z) == (5, -3, 7)
    assert (b.x, b.y, b.z) == (6, -3, 7)


def test_negative_coordinates():
    corner1, corner2 = (-2, -2, -2), (-1, -1, -1)
    packed = "mcl_core:stone|1,0,0x8"

    nodes = _decode_nodes(packed, corner1, corner2, luanti=None)

    assert [(n.x, n.y, n.z) for n in nodes][0] == (-2, -2, -2)
    assert [(n.x, n.y, n.z) for n in nodes][-1] == (-1, -1, -1)


def test_a_single_node_region():
    nodes = _decode_nodes("air|1,0,0x1", (3, 4, 5), (3, 4, 5), luanti=None)
    assert len(nodes) == 1 and (nodes[0].x, nodes[0].y, nodes[0].z) == (3, 4, 5)


def test_the_luanti_instance_is_bound_so_inventory_works():
    sentinel = object()
    nodes = _decode_nodes("air|1,0,0x1", (0, 0, 0), (0, 0, 0), luanti=sentinel)
    assert nodes[0]._luanti is sentinel


@pytest.mark.parametrize("packed, why", [
    ("no separator here", "no pipe at all"),
    ("air|1,0,0x7", "run count does not fill the region"),
    ("air|1,0,0x1 1,0,0x1 1,0,0x1", "too many nodes"),
    ("air|9,0,0x8", "palette index that does not exist"),
    ("air|nonsense", "not a token"),
    ("air|1,0x8", "token is missing a field"),
])
def test_a_malformed_answer_is_reported_not_guessed(packed, why):
    with pytest.raises(DataError):
        _decode_nodes(packed, (0, 0, 0), (1, 1, 1), luanti=None)


class _FakeLua:
    def __init__(self, answer) -> None:
        self.answer = answer
        self.calls = []

    def run(self, code, timeout=None):
        self.calls.append(code)
        return self.answer

    def dumps(self, value):
        return repr(value)


class _FakeLuanti:
    def __init__(self, answer) -> None:
        self.lua = _FakeLua(answer)


def _nodes_with(answer) -> Nodes:
    n = Nodes.__new__(Nodes)
    n.lt = _FakeLuanti(answer)
    return n


def test_get_sorts_the_corners_before_walking_them():
    """Given the far corner first, the region and the order must be the same."""
    forwards = _nodes_with("mcl_core:stone|1,0,0x8")
    backwards = _nodes_with("mcl_core:stone|1,0,0x8")

    a = forwards.get([Point(0, 0, 0), Point(1, 1, 1)])
    b = backwards.get([Point(1, 1, 1), Point(0, 0, 0)])

    assert [(n.x, n.y, n.z) for n in a] == [(n.x, n.y, n.z) for n in b]
    assert (a[0].x, a[0].y, a[0].z) == (0, 0, 0)


def test_get_of_a_cuboid_is_one_round_trip():
    nodes = _nodes_with("mcl_core:stone|1,0,0x1000")
    result = nodes.get([Point(0, 0, 0), Point(9, 9, 9)])

    assert len(result) == 1000
    assert len(nodes.lt.lua.calls) == 1, "the whole region in one call"


def test_a_node_counts_as_a_corner():
    nodes = _nodes_with("air|1,0,0x8")
    assert len(nodes.get([Node(0, 0, 0), Node(1, 1, 1)])) == 8
