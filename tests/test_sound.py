"""
Sound against a fake server: the Lua that would have gone out is read, not sent.

Nothing here waits for an answer, so there is nothing to emulate on the other side - the
test is whether the parameters a beginner writes turn into the fields Luanti's sound
parameter table actually reads.
"""
import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from miney.lua import Lua
from miney.point import Point
from miney.sound import Sound


_PLAY = re.compile(r"minetest\.sound_play\((\"[^\"]*\"), (\{.*\}|p)\)")
_PARAMS = re.compile(r"local p = (\{.*?\}) p\.object")
_KEY = re.compile(r"(\w+)=")


def _table(lua: str) -> dict:
    """
    One table out of ``lua.dumps`` output, as Python.

    ponytail: JSON is close enough to a Lua table for what this module writes - named
    keys, numbers, strings and booleans. It would not survive a list, and nothing here
    sends one.
    """
    return json.loads(_KEY.sub(r'"\1":', lua).replace("nil", "null"))


class FakeServer:
    """Keeps the Lua it was given, and nothing else."""

    def __init__(self):
        self.calls: list[str] = []
        self.waits: list[bool] = []

    def run(self, code: str, timeout=None, execution_id=None, wait=True):
        self.calls.append(code)
        self.waits.append(wait)
        return None

    @property
    def name(self) -> str:
        """The sound name from the last play()."""
        return json.loads(_PLAY.search(self.calls[-1]).group(1))

    @property
    def params(self) -> dict:
        """The parameter table from the last play()."""
        last = self.calls[-1]
        written = _PARAMS.search(last) or _PLAY.search(last)
        return _table(written.group(1) if _PARAMS.search(last) else written.group(2))


@pytest.fixture
def sound() -> Sound:
    luanti = MagicMock()
    server = FakeServer()
    luanti.lua = MagicMock()
    luanti.lua.run.side_effect = server.run
    luanti.lua.dumps.side_effect = Lua.dumps.__get__(luanti.lua)
    made = Sound(luanti)
    made.fake = server
    return made


# --- what a beginner writes -----------------------------------------------------


def test_one_name_is_enough(sound: Sound):
    sound.play("mcl_portals_open")
    assert sound.fake.name == "mcl_portals_open"
    assert sound.fake.params == {"gain": 1.0, "pitch": 1.0}


def test_nothing_is_sent_that_was_not_asked_for(sound: Sound):
    """No place, no loop, no fade - the engine's own defaults are fine."""
    sound.play("mcl_portals_open")
    params = sound.fake.params
    for field in ("pos", "loop", "fade", "start_time", "max_hear_distance", "to_player"):
        assert field not in params


def test_an_uploaded_sound_keeps_its_name_and_loses_its_extension(sound: Sound):
    """lt.assets.upload() answers with a file name, sound_play wants a group name."""
    sound.play("miney_3f9a1c7b2e04.ogg")
    assert sound.fake.name == "miney_3f9a1c7b2e04"


def test_a_place_makes_it_quieter_further_away(sound: Sound):
    sound.play("mcl_portals_open", point=Point(10, 20, 30))
    assert sound.fake.params["pos"] == {"x": 10.0, "y": 20.0, "z": 30.0}


def test_loud_and_deep(sound: Sound):
    sound.play("mcl_portals_open", gain=0.4, pitch=0.5)
    assert sound.fake.params["gain"] == 0.4
    assert sound.fake.params["pitch"] == 0.5


def test_a_loop_says_so(sound: Sound):
    sound.play("mcl_portals_open", loop=True)
    assert sound.fake.params["loop"] is True


def test_fading_in_and_starting_late(sound: Sound):
    sound.play("mcl_portals_open", fade=0.5, start=2)
    assert sound.fake.params["fade"] == 0.5
    assert sound.fake.params["start_time"] == 2.0


# --- who hears it, and where it comes from --------------------------------------


def test_one_player_only(sound: Sound):
    player = MagicMock()
    player.name = "Steve"
    sound.play("mcl_portals_open", player=player)
    assert sound.fake.params["to_player"] == "Steve"


def test_a_name_works_as_well(sound: Sound):
    sound.play("mcl_portals_open", player="Steve")
    assert sound.fake.params["to_player"] == "Steve"


def test_following_a_player_looks_them_up_on_the_other_side(sound: Sound):
    """An ObjectRef cannot be serialised, so the name travels and the lookup happens
    there - guarded, because the player may have left in the meantime."""
    sound.play("mcl_portals_open", follow="Steve")
    code = sound.fake.calls[-1]
    assert 'minetest.get_player_by_name("Steve")' in code
    assert "if who then" in code
    assert "p.object = who" in code


def test_a_followed_sound_still_carries_its_parameters(sound: Sound):
    sound.play("mcl_portals_open", follow="Steve", gain=0.4, loop=True)
    assert sound.fake.params == {"gain": 0.4, "pitch": 1.0, "loop": True}


def test_the_two_can_be_combined(sound: Sound):
    """Only Steve hears the sound, and it comes from where Alice is."""
    sound.play("mcl_portals_open", player="Steve", follow="Alice")
    assert sound.fake.params["to_player"] == "Steve"
    assert 'minetest.get_player_by_name("Alice")' in sound.fake.calls[-1]


def test_distance_needs_somewhere_to_measure_from(sound: Sound):
    sound.play("mcl_portals_open", point=Point(0, 0, 0), distance=8)
    assert sound.fake.params["max_hear_distance"] == 8.0


# --- the escape hatch -----------------------------------------------------------


def test_extra_fields_go_straight_through(sound: Sound):
    sound.play("mcl_portals_open", exclude_player="Bob")
    assert sound.fake.params["exclude_player"] == "Bob"


def test_extra_may_not_say_what_a_parameter_already_says(sound: Sound):
    with pytest.raises(ValueError) as exc:
        sound.play("mcl_portals_open", to_player="Steve")
    assert "player" in str(exc.value)


# --- input it should not accept -------------------------------------------------


def test_a_place_and_a_player_to_follow_are_a_contradiction(sound: Sound):
    with pytest.raises(ValueError) as exc:
        sound.play("mcl_portals_open", point=Point(0, 0, 0), follow="Steve")
    assert "follow" in str(exc.value)


def test_distance_without_a_place_is_refused(sound: Sound):
    """The engine ignores it silently, which is worse than saying so."""
    with pytest.raises(ValueError) as exc:
        sound.play("mcl_portals_open", distance=8)
    assert "point" in str(exc.value)


def test_a_sound_is_a_name(sound: Sound):
    with pytest.raises(TypeError) as exc:
        sound.play(42)
    assert "lt.assets.sounds" in str(exc.value)


def test_an_empty_name_plays_nothing_and_says_so(sound: Sound):
    with pytest.raises(ValueError):
        sound.play(".ogg")


def test_pitch_is_a_factor(sound: Sound):
    with pytest.raises(ValueError) as exc:
        sound.play("mcl_portals_open", pitch=0)
    assert "pitch" in str(exc.value)


def test_gain_cannot_be_negative(sound: Sound):
    with pytest.raises(ValueError):
        sound.play("mcl_portals_open", gain=-1)


def test_a_word_is_not_a_volume(sound: Sound):
    with pytest.raises(TypeError) as exc:
        sound.play("mcl_portals_open", gain="loud")
    assert "gain" in str(exc.value)


def test_a_number_is_not_a_player(sound: Sound):
    with pytest.raises(TypeError) as exc:
        sound.play("mcl_portals_open", player=7)
    assert "lt.players" in str(exc.value)


def test_a_place_is_a_point(sound: Sound):
    with pytest.raises(TypeError) as exc:
        sound.play("mcl_portals_open", point=(10, 20, 30))
    assert "Point" in str(exc.value)


def test_nothing_reaches_the_server_after_a_refusal(sound: Sound):
    with pytest.raises(ValueError):
        sound.play("mcl_portals_open", pitch=0)
    assert sound.fake.calls == []


# --- stopping again -------------------------------------------------------------


def test_every_sound_gets_its_own_key(sound: Sound):
    first = sound.play("mcl_portals_open")
    second = sound.play("mcl_portals_open")
    assert first.key != second.key
    assert first.key in sound.fake.calls[0]


def test_stop_ends_the_one_it_started(sound: Sound):
    playing = sound.play("mcl_portals_open")
    playing.stop()
    last = sound.fake.calls[-1]
    assert "minetest.sound_stop(id)" in last
    assert playing.key in last


def test_a_fade_out_counts_down_from_the_volume_it_started_at(sound: Sound):
    """Luanti fades by gain per second, so a quiet sound has to fall more slowly to
    take the same three seconds."""
    sound.play("mcl_portals_open", gain=0.6).fade_out(3)
    assert "minetest.sound_fade(id, 0.2, 0)" in sound.fake.calls[-1]


def test_a_fade_over_no_time_is_not_a_fade(sound: Sound):
    with pytest.raises(ValueError) as exc:
        sound.play("mcl_portals_open").fade_out(0)
    assert "stop()" in str(exc.value)


def test_stop_all_walks_the_whole_table(sound: Sound):
    sound.play("mcl_portals_open")
    sound.stop_all()
    last = sound.fake.calls[-1]
    assert "pairs(miney_sounds)" in last
    assert "miney_sounds = {}" in last


def test_a_with_block_stops_on_the_way_out(sound: Sound):
    with sound.play("mcl_portals_open", loop=True) as music:
        assert "sound_stop" not in sound.fake.calls[-1]
    assert music.key in sound.fake.calls[-1]


# --- how it talks ---------------------------------------------------------------


def test_nothing_here_waits_for_the_server(sound: Sound):
    """A loop of sounds should cost no server steps at all."""
    sound.play("mcl_portals_open").stop()
    sound.stop_all()
    assert sound.fake.waits == [False, False, False]


def test_it_says_which_sound_it_is(sound: Sound):
    assert repr(sound.play("mcl_portals_open")) == '<Luanti PlayingSound "sound-1">'
    assert repr(sound) == "<Luanti Sound>"


# --- the sounds the mod brings along ---------------------------------------------


SOUND_DIR = Path(__file__).resolve().parent.parent / "mod_data" / "miney" / "sounds"


def _shipped() -> list[Path]:
    return sorted(SOUND_DIR.glob("*.ogg"))


def test_the_mod_ships_sounds_to_play():
    """Without these, every example in the docs needs a name only one game happens to
    know."""
    assert len(_shipped()) >= 40


def test_every_shipped_sound_is_named_for_a_python_attribute():
    """The name reaches the user as lt.assets.sounds.miney.<rest>, so an upper case
    letter or a dash would be a name nobody can type."""
    for path in _shipped():
        assert re.fullmatch(r"miney_[a-z0-9_]+\.ogg", path.name), path.name


def test_every_shipped_sound_is_mono():
    """Luanti positions single-channel audio only (doc/lua_api.md), so a stereo file
    would ignore point= and follow= without saying anything."""
    for path in _shipped():
        raw = path.read_bytes()
        header = raw.find(b"\x01vorbis")
        assert header != -1, f"{path.name} is not Ogg Vorbis"
        assert raw[header + 11] == 1, f"{path.name} is not mono"


def test_the_sounds_carry_their_credit():
    assert "Kenney" in (SOUND_DIR / "README.md").read_text(encoding="utf-8")
