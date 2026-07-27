"""
Hud against a fake server: the ``miney_hud`` half of the mod, in Python.
"""
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from miney.exceptions import HudElementGone, PlayerOffline
from miney.hud import Hud, POSITIONS
from miney.lua import Lua
from miney.point import Point


_SET = re.compile(r'^return miney_hud\.set\("([^"]*)", (nil|"[^"]*"), "(\w+)", (\{.*\})\)$')
_CHANGE = re.compile(r'^return miney_hud\.change\("([^"]*)", "([^"]*)", (\{.*\})\)$')


class FakeHud:
    """
    The mod side, as far as ``Hud`` can tell.

    Keeps the one piece of state that really lives there: the named registry per
    player. Element names are invented here, the way the mod does it, because a
    Python-side counter would start at 1 again with every script.
    """

    def __init__(self, flags=None, online=True):
        self.calls: list[str] = []
        self.sets: list[tuple[str, str, str, str]] = []
        self.changes: list[tuple[str, str, str]] = []
        self.elements: dict[str, str] = {}  # name -> kind
        self.counters: dict[str, int] = {}
        self.removed: list[str] = []
        self.cleared = 0
        self.flags = flags or {
            "hotbar": True, "healthbar": True, "breathbar": True, "crosshair": True,
            "wielditem": True, "minimap": True, "minimap_radar": True,
            "basic_debug": True, "chat": True,
        }
        self.hotbar = {"slots": 8, "image": "", "selected_image": ""}
        self.online = online

    def run(self, code: str):
        self.calls.append(code)
        if not self.online:
            return None

        match = _SET.match(code)
        if match:
            player, name, kind, definition = match.groups()
            self.sets.append((player, name, kind, definition))
            if name == "nil":
                self.counters[kind] = self.counters.get(kind, 0) + 1
                name = f"{kind}_{self.counters[kind]}"
            else:
                name = name.strip('"')
            self.elements[name] = kind
            return {"name": name}

        match = _CHANGE.match(code)
        if match:
            _, name, definition = match.groups()
            if name not in self.elements:
                return {"error": f'This HUD element is gone: "{name}".', "kind": "gone"}
            self.changes.append((name, definition, code))
            return {"ok": True}

        if code.startswith("return miney_hud.remove("):
            name = code[:-1].rsplit('"', 2)[1]
            self.removed.append(name)
            self.elements.pop(name, None)
            return True

        if code.startswith("return miney_hud.clear("):
            self.cleared += 1
            self.elements.clear()
            return True

        if code.startswith("return miney_hud.flags("):
            return dict(self.flags)

        if code.startswith("return miney_hud.set_flags("):
            for key, value in re.findall(r"(\w+)=(true|false)", code):
                self.flags[key] = value == "true"
            return True

        if code.startswith("return miney_hud.hotbar("):
            field = re.search(r'", "(\w+)"', code).group(1)
            value = code[:-1].split(", ", 2)[2]
            if value == "nil":
                return self.hotbar[field]
            self.hotbar[field] = int(value) if value.isdigit() else value.strip('"')
            return True

        raise AssertionError(f"unexpected Lua: {code!r}")


def make_hud(**kwargs) -> Hud:
    luanti = MagicMock()
    fake = FakeHud(**kwargs)
    luanti.lua = MagicMock()
    luanti.lua.run.side_effect = fake.run
    luanti.lua.dumps.side_effect = Lua.dumps.__get__(luanti.lua)
    luanti.assets.upload.return_value = "miney_deadbeef0000.png"
    player = MagicMock()
    player.name = "Steve"
    player.lt = luanti
    hud = Hud(luanti, player)
    hud.fake = fake
    return hud


@pytest.fixture
def hud() -> Hud:
    return make_hud()


def definition_of(hud: Hud, index: int = 0) -> str:
    """The Lua table one add() sent, as text."""
    return hud.fake.sets[index][3]


# --- the handle -----------------------------------------------------------------


def test_text_puts_something_on_the_screen(hud: Hud):
    element = hud.text("Welcome!")
    assert 'text="Welcome!"' in definition_of(hud)
    assert element.name == "text_1"
    assert element.kind == "text"


def test_the_handle_says_what_it_is(hud: Hud):
    element = hud.text("Score: 0", name="score")
    assert repr(element) == '<HudElement "score" (text) for "Steve">'


def test_a_second_element_without_a_name_gets_its_own(hud: Hud):
    assert hud.text("one").name == "text_1"
    assert hud.text("two").name == "text_2"


def test_the_same_name_twice_is_one_element(hud: Hud):
    hud.text("Score: 0", name="score")
    hud.text("Score: 7", name="score")
    assert list(hud.fake.elements) == ["score"]


def test_writing_a_field_changes_it_on_the_server(hud: Hud):
    element = hud.text("Score: 0", name="score")
    element.text = "Score: 7"
    assert hud.fake.changes[0][0] == "score"
    assert 'text="Score: 7"' in hud.fake.changes[0][1]


def test_reading_a_field_answers_from_memory(hud: Hud):
    """Luanti offers no way to read a HUD element back, so this never asks."""
    element = hud.text("Score: 0", name="score")
    before = len(hud.fake.calls)
    assert element.text == "Score: 0"
    assert len(hud.fake.calls) == before


def test_writing_to_an_element_that_is_gone_says_so(hud: Hud):
    element = hud.text("Score: 0", name="score")
    hud.clear()
    with pytest.raises(HudElementGone):
        element.text = "Score: 7"


def test_removing_an_element_that_is_gone_is_not_an_error(hud: Hud):
    """The goal is already reached, so there is nothing to complain about."""
    element = hud.text("gone", name="ghost")
    hud.clear()
    element.remove()


# --- Luanti's field names are translated ----------------------------------------


def test_color_becomes_a_number(hud: Hud):
    hud.text("hi", color="#ffcc00")
    assert f"number={0xffcc00}" in definition_of(hud)


def test_a_colour_that_is_not_one_names_what_works(hud: Hud):
    with pytest.raises(ValueError) as exc:
        hud.text("hi", color="gold")
    assert "#rrggbb" in str(exc.value)


def test_texture_becomes_text(hud: Hud):
    hud.image("default_dirt.png")
    assert 'text="default_dirt.png"' in definition_of(hud)


def test_value_and_max_value_become_number_and_item(hud: Hud):
    hud.statbar("heart.png", value=10, max_value=20)
    definition = definition_of(hud)
    assert "number=10" in definition
    assert "item=20" in definition


def test_max_value_brings_its_own_off_state_texture(hud: Hud):
    """Without text2 Luanti draws nothing for the 'off' half, and item does nothing."""
    hud.statbar("heart.png", value=10, max_value=20)
    assert 'text2="heart.png"' in definition_of(hud)


def test_a_waypoints_label_is_luantis_name_field(hud: Hud):
    hud.waypoint(Point(10, 20, 30), "Base")
    definition = definition_of(hud)
    assert 'name="Base"' in definition
    assert "world_pos={x=10, y=20, z=30}" in definition


def test_bold_and_italic_become_one_style_bitfield(hud: Hud):
    hud.text("hi", bold=True, italic=True)
    assert "style=3" in definition_of(hud)


def test_list_name_and_slots_become_text_and_number(hud: Hud):
    hud.inventory("main", slots=8)
    definition = definition_of(hud)
    assert 'text="main"' in definition
    assert "number=8" in definition


# --- positions ------------------------------------------------------------------


def test_a_position_name_becomes_a_fraction(hud: Hud):
    hud.text("hi", position="top left")
    assert "position={x=0.0, y=0.0}" in definition_of(hud)


def test_a_position_also_sets_the_alignment_that_keeps_it_on_screen(hud: Hud):
    """Luanti draws from the position outwards, so a corner needs to point inwards."""
    hud.text("hi", position="bottom right")
    definition = definition_of(hud)
    assert "position={x=1.0, y=1.0}" in definition
    assert "alignment={x=-1.0, y=-1.0}" in definition


def test_the_default_position_is_the_middle_of_the_screen(hud: Hud):
    hud.text("hi")
    assert "position={x=0.5, y=0.5}" in definition_of(hud)


def test_a_tuple_places_it_freely(hud: Hud):
    hud.text("hi", position=(0.25, 0.75))
    assert "position={x=0.25, y=0.75}" in definition_of(hud)


def test_an_unknown_position_lists_the_ones_that_work(hud: Hud):
    with pytest.raises(ValueError) as exc:
        hud.text("hi", position="middle")
    for name in POSITIONS:
        assert name in str(exc.value)


def test_a_waypoint_is_placed_by_the_world_and_not_by_the_screen(hud: Hud):
    with pytest.raises(ValueError) as exc:
        hud.waypoint(Point(1, 2, 3), "Base", position="top")
    assert "position" in str(exc.value)


# --- scale ----------------------------------------------------------------------


def test_one_number_scales_both_axes(hud: Hud):
    hud.image("dirt.png", scale=4)
    assert "scale={x=4, y=4}" in definition_of(hud)


def test_a_negative_scale_is_a_share_of_the_screen(hud: Hud):
    hud.image("dirt.png", scale=(-50, -50))
    assert "scale={x=-50, y=-50}" in definition_of(hud)


# --- pictures -------------------------------------------------------------------


def test_a_texture_name_is_used_as_it_is(hud: Hud):
    hud.image("default_dirt.png")
    assert not hud.lt.assets.upload.called


def test_anything_that_is_not_a_name_is_uploaded_first(hud: Hud):
    hud.image(Path("cat.png"))
    hud.lt.assets.upload.assert_called_once()
    assert 'text="miney_deadbeef0000.png"' in definition_of(hud)


# --- the built-in HUD -----------------------------------------------------------


def test_a_flag_reads_from_the_server(hud: Hud):
    assert hud.healthbar is True


def test_a_flag_writes_to_the_server(hud: Hud):
    hud.healthbar = False
    assert hud.fake.flags["healthbar"] is False
    assert hud.healthbar is False


def test_a_flag_is_a_yes_or_no(hud: Hud):
    with pytest.raises(TypeError):
        hud.crosshair = "off"


def test_hotbar_slots_round_trip(hud: Hud):
    hud.hotbar_slots = 4
    assert hud.hotbar_slots == 4


def test_hotbar_slots_names_the_range_it_accepts(hud: Hud):
    with pytest.raises(ValueError) as exc:
        hud.hotbar_slots = 40
    assert "1" in str(exc.value) and "32" in str(exc.value)


def test_clear_takes_everything_down(hud: Hud):
    hud.text("one")
    hud.text("two")
    hud.clear()
    assert hud.fake.cleared == 1
    assert hud.fake.elements == {}


# --- the player has to be there -------------------------------------------------


def test_an_offline_player_says_so():
    hud = make_hud(online=False)
    with pytest.raises(PlayerOffline):
        hud.text("nobody is there")


def test_reading_a_flag_from_an_offline_player_says_so():
    hud = make_hud(online=False)
    with pytest.raises(PlayerOffline):
        hud.healthbar
