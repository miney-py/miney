"""
Sky against a fake server: Luanti's sky half, in Python.

Every write goes to ``miney_sky.hold()`` in the mod, which applies it and remembers it,
so this fake plays that function. It copies the one piece of behaviour the whole class
rests on and which the mod repeats deliberately: a part starts from what the player
already has and only the fields that were sent change
(``src/script/lua_api/l_object.cpp:2218`` and the four next to it). Setting the clouds
therefore has to leave the colour alone, and that is a test rather than a comment.
"""
import re
import struct
from unittest.mock import MagicMock

import pytest

from miney.exceptions import PlayerOffline
from miney.lua import Lua
from miney.sky import Sky


_HOLD = re.compile(r'miney_sky\.hold\("([^"]+)", "(\w+)", (.+)\)$')
_RELEASE = re.compile(r'miney_sky\.release\("([^"]+)"\)$')
_FIELD = re.compile(r'(\w+)=("[^"]*"|true|false|-?[\d.]+)')

WHITE = {"r": 255, "g": 255, "b": 255, "a": 255}


def _float32(number: float) -> float:
    """The number as a C ``float`` reads back in Python."""
    return struct.unpack("f", struct.pack("f", number))[0]


def _value(text: str):
    """One Lua literal out of a table, as Python."""
    if text.startswith('"'):
        return text.strip('"')
    if text in ("true", "false"):
        return text == "true"
    return float(text)


class FakeSky:
    """The sky Luanti keeps for one player, as far as :class:`Sky` can tell."""

    DEFAULTS = {
        "sky": {"type": "regular", "base_color": WHITE, "clouds": True},
        "sun": {"visible": True, "sunrise_visible": True},
        "moon": {"visible": True},
        "stars": {"visible": True},
    }

    def __init__(self, online: bool = True):
        self.online = online
        self.calls: list[str] = []
        self.state = {name: dict(fields) for name, fields in self.DEFAULTS.items()}
        self.ratio = None

    def run(self, code: str, timeout=None, execution_id=None, wait=True):
        self.calls.append(code)
        if not self.online:
            return None
        held = _HOLD.match(code)
        if held:
            self._set(held.group(2), held.group(3))
            return None
        if _RELEASE.match(code):
            self.state = {name: dict(fields)
                          for name, fields in self.DEFAULTS.items()}
            self.ratio = None
            return None
        return self._get(code)

    def _set(self, what: str, arguments: str) -> None:
        if what == "ratio":
            # The engine keeps it as a 32 bit float, so 0.05 reads back as
            # 0.05000000074505806 (`m_day_night_ratio`, a float, in player.h). A real
            # server does this and the fake has to, or the rounding in the getter has
            # nothing to catch here.
            self.ratio = None if arguments == "nil" else _float32(float(arguments))
            return
        # The merge: only the fields that were sent change.
        for field, literal in _FIELD.findall(arguments):
            value = _value(literal)
            if field == "base_color":
                number = int(value.lstrip("#"), 16)
                value = {
                    "r": (number >> 16) & 0xFF,
                    "g": (number >> 8) & 0xFF,
                    "b": number & 0xFF,
                    "a": 255,
                }
            self.state[what][field] = value

    def _get(self, code: str) -> dict:
        if "get_day_night_ratio()" in code:
            return {"online": True, "ratio": self.ratio}
        if "get_sky(true)" in code:
            sky = self.state["sky"]
            return {
                "online": True,
                "type": sky["type"],
                "color": sky["base_color"],
                "clouds": sky["clouds"],
            }
        for what in ("sun", "moon", "stars"):
            if f"get_{what}()" in code:
                return {"online": True, what: self.state[what]["visible"]}
        raise AssertionError(f"unexpected Lua: {code!r}")


def make_sky(**kwargs) -> Sky:
    luanti = MagicMock()
    fake = FakeSky(**kwargs)
    luanti.lua = MagicMock()
    luanti.lua.run.side_effect = fake.run
    luanti.lua.dumps.side_effect = Lua.dumps.__get__(luanti.lua)
    player = MagicMock()
    player.name = "Steve"
    player.lt = luanti
    sky = Sky(luanti, player)
    sky.fake = fake
    sky.mock_run = luanti.lua.run
    return sky


@pytest.fixture
def sky() -> Sky:
    return make_sky()


# --- the colour -----------------------------------------------------------------


def test_a_colour_makes_the_sky_plain(sky: Sky):
    sky.color = "#101040"
    assert sky.fake.state["sky"]["type"] == "plain"
    assert sky.color == "#101040"


def test_the_painted_sky_has_no_one_colour(sky: Sky):
    """A "regular" sky is blue at noon and red at sunset, so there is nothing to give."""
    assert sky.color is None


def test_none_gives_the_painted_sky_back(sky: Sky):
    sky.color = "#101040"
    sky.color = None
    assert sky.fake.state["sky"]["type"] == "regular"
    assert sky.color is None


def test_a_number_is_a_colour_too(sky: Sky):
    sky.color = 0x101040
    assert sky.color == "#101040"


def test_setting_the_clouds_leaves_the_colour_alone(sky: Sky):
    """Luanti's setters merge. If they did not, this would be a white sky."""
    sky.color = "#101040"
    sky.clouds = False
    assert sky.color == "#101040"
    assert sky.clouds is False


# --- what hangs in it -----------------------------------------------------------


def test_clouds_go_away_and_come_back(sky: Sky):
    sky.clouds = False
    assert sky.clouds is False
    sky.clouds = True
    assert sky.clouds is True


def test_the_sun_takes_the_sunrise_with_it(sky: Sky):
    """Left on its own, Luanti keeps colouring the sunrise for a sun that is gone."""
    sky.sun = False
    assert sky.fake.state["sun"] == {"visible": False, "sunrise_visible": False}
    assert sky.sun is False


def test_moon_and_stars(sky: Sky):
    sky.moon = False
    sky.stars = False
    assert sky.moon is False
    assert sky.stars is False


# --- brightness -----------------------------------------------------------------


def test_brightness_is_night_at_noon(sky: Sky):
    sky.brightness = 0.05
    assert sky.brightness == 0.05


def test_the_day_decides_until_it_is_told_otherwise(sky: Sky):
    assert sky.brightness is None


def test_none_hands_the_day_back(sky: Sky):
    sky.brightness = 0.05
    sky.brightness = None
    assert sky.brightness is None
    assert sky.fake.calls[-2] == 'miney_sky.hold("Steve", "ratio", nil)'


# --- reset ----------------------------------------------------------------------


def test_reset_puts_everything_back_in_one_call(sky: Sky):
    sky.color = "#101040"
    sky.clouds = False
    sky.sun = False
    sky.stars = False
    sky.brightness = 0.05

    before = len(sky.fake.calls)
    sky.reset()
    assert len(sky.fake.calls) == before + 1

    assert sky.color is None
    assert sky.clouds is True
    assert sky.sun is True
    assert sky.stars is True
    assert sky.brightness is None


# --- games that paint their own sky ----------------------------------------------


def test_a_write_asks_the_mod_to_hold_it(sky: Sky):
    """VoxeLibre repaints every player's sky about once a second, so a colour the mod
    does not hold is gone before the next line of a script runs."""
    sky.color = "#101040"
    assert sky.fake.calls[-1] == (
        'miney_sky.hold("Steve", "sky", {type="plain", base_color="#101040"})'
    )


def test_reset_gives_the_sky_back(sky: Sky):
    sky.color = "#101040"
    sky.reset()
    assert sky.fake.calls[-1] == 'miney_sky.release("Steve")'


def test_only_this_player_is_named(sky: Sky):
    """The whole point of going through the mod: a sky belongs to one player, so no
    call may reach for a setting the rest of the world shares."""
    sky.color = "#101040"
    sky.brightness = 0.05
    sky.reset()
    for call in sky.fake.calls:
        assert "Steve" in call
        assert "mcl_weather" not in call


# --- input it should not accept -------------------------------------------------


def test_a_colour_that_is_not_one_names_what_works(sky: Sky):
    with pytest.raises(ValueError) as exc:
        sky.color = "midnight"
    assert "#rrggbb" in str(exc.value)


@pytest.mark.parametrize("field", ["clouds", "sun", "moon", "stars"])
def test_only_true_or_false(sky: Sky, field: str):
    with pytest.raises(TypeError) as exc:
        setattr(sky, field, 1)
    assert field in str(exc.value)


def test_a_brightness_outside_the_day_says_the_range(sky: Sky):
    with pytest.raises(ValueError) as exc:
        sky.brightness = 2
    assert "between 0" in str(exc.value)


def test_true_is_not_a_brightness(sky: Sky):
    """It would arrive as 1, which is noon, and nobody meant that."""
    with pytest.raises(TypeError):
        sky.brightness = True


def test_nothing_reaches_the_server_after_a_refusal(sky: Sky):
    with pytest.raises(ValueError):
        sky.color = "midnight"
    assert sky.fake.calls == []


# --- the player who left --------------------------------------------------------


@pytest.mark.parametrize("field", ["color", "clouds", "sun", "moon", "stars",
                                   "brightness"])
def test_reading_an_offline_players_sky_says_so(field: str):
    sky = make_sky(online=False)
    with pytest.raises(PlayerOffline) as exc:
        getattr(sky, field)
    assert "Steve" in str(exc.value)


# --- how it talks ---------------------------------------------------------------


def test_setting_does_not_wait_for_the_server(sky: Sky):
    """Like every other Player setter: send it and carry on."""
    sky.clouds = False
    assert sky.mock_run.call_args.kwargs["wait"] is False


def test_reading_waits(sky: Sky):
    sky.clouds
    assert "wait" not in sky.mock_run.call_args.kwargs


def test_it_says_whose_sky_it_is(sky: Sky):
    assert repr(sky) == '<Luanti Sky for "Steve">'
