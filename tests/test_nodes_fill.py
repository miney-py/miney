"""lt.nodes.fill: the box it describes, and the slabs it is cut into."""
from __future__ import annotations
import pytest

from miney.nodes import Nodes, _slabs, _MAX_FILL_VOLUME
from miney.node import Node
from miney.point import Point


class _FakeLua:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run(self, code, timeout=None):
        self.calls.append(code)
        # The real Lua returns how many blocks it wrote; the box is in the source.
        p1 = [int(code.split(f"{axis} = ")[1].split(",")[0].split("}")[0])
              for axis in ("x", "y", "z")]
        p2 = [int(code.split(f"{axis} = ")[2].split(",")[0].split("}")[0])
              for axis in ("x", "y", "z")]
        return (p2[0] - p1[0] + 1) * (p2[1] - p1[1] + 1) * (p2[2] - p1[2] + 1)

    def dumps(self, value):
        return repr(value)


class _FakeLuanti:
    def __init__(self) -> None:
        self.lua = _FakeLua()


@pytest.fixture
def nodes() -> Nodes:
    n = Nodes.__new__(Nodes)
    n.lt = _FakeLuanti()
    n._names_cache = ["air", "mcl_core:obsidian", "mcl_core:stone"]
    return n


def _volume(box) -> int:
    (x1, y1, z1), (x2, y2, z2) = box
    return (x2 - x1 + 1) * (y2 - y1 + 1) * (z2 - z1 + 1)


def _cells(box) -> set:
    (x1, y1, z1), (x2, y2, z2) = box
    return {(x, y, z)
            for x in range(x1, x2 + 1)
            for y in range(y1, y2 + 1)
            for z in range(z1, z2 + 1)}


@pytest.mark.parametrize("p1, p2", [
    ((0, 0, 0), (0, 0, 0)),
    ((0, 0, 0), (9, 4, 9)),
    ((-5, -5, -5), (5, 5, 5)),
    ((0, 0, 0), (99, 0, 99)),
])
def test_small_boxes_are_one_slab_and_cover_themselves(p1, p2):
    boxes = list(_slabs(p1, p2))
    assert len(boxes) == 1
    assert _cells(boxes[0]) == _cells((p1, p2))


def test_a_big_box_is_cut_up_and_still_covers_exactly():
    p1, p2 = (0, 0, 0), (299, 99, 299)          # 9,000,000 blocks
    boxes = list(_slabs(p1, p2))

    assert len(boxes) > 1, "should have been split"
    assert all(_volume(b) <= _MAX_FILL_VOLUME for b in boxes), "a slab is too big"
    assert sum(_volume(b) for b in boxes) == 300 * 100 * 300, "gap or overlap"

    seen = set()
    for box in boxes:                            # no cell twice
        cells = _cells(box)
        assert not (cells & seen)
        seen |= cells
    assert len(seen) == 300 * 100 * 300


def test_a_box_too_wide_for_one_layer_is_cut_along_y_as_well():
    """dx*dy alone exceeds the budget, so slicing z is not enough."""
    p1, p2 = (0, 0, 0), (2999, 2999, 1)
    boxes = list(_slabs(p1, p2))

    assert all(_volume(b) <= _MAX_FILL_VOLUME for b in boxes)
    assert sum(_volume(b) for b in boxes) == 3000 * 3000 * 2


def test_fill_counts_every_block_of_a_split_box(nodes):
    written = nodes.fill(Point(0, 0, 0), Point(299, 99, 299), "air")
    assert written == 300 * 100 * 300
    assert len(nodes.lt.lua.calls) > 1


def test_the_corners_may_be_given_in_any_order(nodes):
    forwards = nodes.fill(Point(0, 10, 0), Point(9, 14, 9), "air")
    backwards = nodes.fill(Point(9, 14, 9), Point(0, 10, 0), "air")
    assert forwards == backwards == 500
    assert nodes.lt.lua.calls[-1] == nodes.lt.lua.calls[-2]


def test_a_node_works_as_a_corner_because_it_is_a_point(nodes):
    assert nodes.fill(Node(0, 0, 0), Node(1, 1, 1), "air") == 8


def test_fractional_coordinates_are_floored_like_everywhere_else(nodes):
    assert nodes.fill(Point(0.9, 0.9, 0.9), Point(1.9, 1.9, 1.9), "air") == 8


def test_an_unknown_block_name_says_where_to_find_a_real_one(nodes):
    with pytest.raises(ValueError, match="lt.nodes.names"):
        nodes.fill(Point(0, 0, 0), Point(1, 1, 1), "mcl_core:obsidain")
    assert nodes.lt.lua.calls == [], "it must not reach the server"


@pytest.mark.parametrize("start, end, name", [
    ((0, 0, 0), Point(1, 1, 1), "air"),
    (Point(0, 0, 0), [1, 1, 1], "air"),
    (Point(0, 0, 0), Point(1, 1, 1), 42),
])
def test_fill_rejects_the_wrong_kind_of_argument(nodes, start, end, name):
    with pytest.raises(TypeError):
        nodes.fill(start, end, name)
