"""The name trees: `lt.nodes.names`, `lt.tool` and `lt.items`.

One class does all three. It exists so a name can be *found* with TAB instead of
remembered, and it is a list and a dictionary as well, because a beginner reaches for
``[0]`` and ``["default:dirt"]`` before they reach for a dotted path.

Indexing used to raise ``AttributeError`` from both trees - the lookup read an attribute
called ``node_types`` that exists nowhere in the package - so most of what is below is
about the thing that never worked.
"""
from __future__ import annotations

import pytest

from miney.items import ItemIterable
from miney.nodes import NameIterable
from miney.tool import ToolIterable


NAMES = ["default:stone", "default:dirt", "mcl_core:sand", "air", "ignore"]


@pytest.fixture
def names() -> NameIterable:
    return NameIterable(NAMES)


def test_a_name_is_two_dots_away(names):
    assert names.default.dirt == "default:dirt"
    assert names.mcl_core.sand == "mcl_core:sand"


def test_names_without_a_mod_sit_at_the_top(names):
    """'air' and 'ignore' are the engine's own and carry no mod in front of them."""
    assert names.air == "air"
    assert names.ignore == "ignore"


def test_it_is_a_list(names):
    assert len(names) == len(NAMES)
    assert sorted(names) == sorted(NAMES)


def test_the_order_is_the_same_every_time(names):
    """Luanti hands the names over out of a Lua table, which has no order to trust."""
    assert list(names) == sorted(NAMES)
    assert names[0] == sorted(NAMES)[0]


def test_a_full_name_can_be_looked_up(names):
    assert names["default:dirt"] == "default:dirt"


def test_a_mod_can_be_looked_up(names):
    assert names["default"].dirt == "default:dirt"


def test_a_short_name_below_a_mod_can_be_looked_up(names):
    assert names.default["dirt"] == "default:dirt"


def test_an_unknown_name_is_a_keyerror(names):
    with pytest.raises(KeyError):
        names["default:nonsense"]
    with pytest.raises(KeyError):
        names.default["nonsense"]


def test_the_insides_are_not_reachable_by_name(names):
    """``names["_names"]`` would otherwise hand out the list it keeps."""
    with pytest.raises(KeyError):
        names["_names"]


def test_a_mod_counts_only_its_own(names):
    assert len(names.default) == 2
    assert sorted(names.default) == ["default:dirt", "default:stone"]


def test_a_mod_does_not_contain_itself(names):
    """Building the levels by recursion would put a 'default' inside 'default'."""
    assert not hasattr(names.default, "default")


def test_nothing_registered_is_an_empty_tree():
    empty = NameIterable()
    assert len(empty) == 0
    assert list(empty) == []


@pytest.mark.parametrize("kind, label", [
    (NameIterable, "names"),
    (ToolIterable, "tools"),
    (ItemIterable, "items"),
])
def test_every_tree_says_what_it_is(kind, label):
    tree = kind(NAMES)
    assert repr(tree) == f"<Luanti {label}: {len(NAMES)}>"


@pytest.mark.parametrize("kind", [ToolIterable, ItemIterable])
def test_the_other_two_trees_work_the_same_way(kind):
    tree = kind(["default:stick", "default:pick_mese"])
    assert tree.default.stick == "default:stick"
    assert tree["default:pick_mese"] == "default:pick_mese"
    assert len(tree) == 2
