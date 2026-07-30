"""
Particles against a fake server: the Lua that would have gone out is read, not sent.

Everything here is one round trip that never waits for an answer, so there is nothing to
emulate on the other side - the test is whether the parameters a beginner writes turn
into the fields Luanti's ParticleSpawner actually reads.
"""
import json
import re
from unittest.mock import MagicMock

import pytest

from miney.lua import Lua
from miney.particles import SPARK, Particles
from miney.point import Point


_DEFINITION = re.compile(r"minetest\.add_particlespawner\((.*)\)$", re.DOTALL)
_KEY = re.compile(r"(\w+)=")


def _table(lua: str) -> dict:
    """
    One table out of ``lua.dumps`` output, as Python.

    ponytail: JSON is close enough to a Lua table for what this module writes - named
    keys, numbers and strings. It would not survive a list, and nothing here sends one.
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
    def definition(self) -> dict:
        """The spawner definition from the last spawn()."""
        return _table(_DEFINITION.search(self.calls[-1]).group(1))


@pytest.fixture
def particles() -> Particles:
    luanti = MagicMock()
    server = FakeServer()
    luanti.lua = MagicMock()
    luanti.lua.run.side_effect = server.run
    luanti.lua.dumps.side_effect = Lua.dumps.__get__(luanti.lua)
    made = Particles(luanti)
    made.fake = server
    return made


# --- what a beginner writes -----------------------------------------------------


def test_one_point_is_enough(particles: Particles):
    particles.spawn(Point(10, 20, 30))
    definition = particles.fake.definition
    assert definition["pos"] == {"x": 10.0, "y": 20.0, "z": 30.0}
    assert definition["amount"] == 100
    assert definition["texture"] == SPARK


def test_nothing_is_sent_that_was_not_asked_for(particles: Particles):
    """No movement means no vel, acc or radius - the engine's defaults are fine."""
    particles.spawn(Point(0, 0, 0))
    definition = particles.fake.definition
    assert "vel" not in definition
    assert "acc" not in definition
    assert "radius" not in definition


def test_a_colour_tints_the_spark(particles: Particles):
    particles.spawn(Point(0, 0, 0), color="#ffcc00")
    assert particles.fake.definition["texture"] == f"{SPARK}^[colorize:#ffcc00:255"


def test_a_number_is_a_colour_too(particles: Particles):
    particles.spawn(Point(0, 0, 0), color=0xFFCC00)
    assert particles.fake.definition["texture"].endswith("^[colorize:#ffcc00:255")


def test_the_games_own_texture_can_be_tinted_as_well(particles: Particles):
    particles.spawn(Point(0, 0, 0), texture="mcl_particles_effect.png", color="#ff6666")
    assert particles.fake.definition["texture"] == (
        "mcl_particles_effect.png^[colorize:#ff6666:255"
    )


# --- the parameters that hide a min-max pair ------------------------------------


def test_spread_is_a_sphere_not_a_cube(particles: Particles):
    particles.spawn(Point(0, 0, 0), spread=2)
    assert particles.fake.definition["radius"] == {"min": 0.0, "max": 2.0}


def test_speed_goes_in_every_direction(particles: Particles):
    particles.spawn(Point(0, 0, 0), speed=3)
    assert particles.fake.definition["vel"] == {
        "min": {"x": -3.0, "y": -3.0, "z": -3.0},
        "max": {"x": 3.0, "y": 3.0, "z": 3.0},
    }


def test_gravity_pulls_down(particles: Particles):
    particles.spawn(Point(0, 0, 0), gravity=4)
    assert particles.fake.definition["acc"] == {"x": 0.0, "y": -4.0, "z": 0.0}


def test_time_and_life_are_two_different_clocks(particles: Particles):
    particles.spawn(Point(0, 0, 0), time=0.2, life=2)
    definition = particles.fake.definition
    assert definition["time"] == 0.2
    assert definition["exptime"] == 2.0


def test_one_player_only(particles: Particles):
    player = MagicMock()
    player.name = "Steve"
    particles.spawn(Point(0, 0, 0), player=player)
    assert particles.fake.definition["playername"] == "Steve"


def test_a_name_works_as_well(particles: Particles):
    particles.spawn(Point(0, 0, 0), player="Steve")
    assert particles.fake.definition["playername"] == "Steve"


# --- the escape hatch -----------------------------------------------------------


def test_extra_fields_go_straight_through(particles: Particles):
    particles.spawn(Point(0, 0, 0), collisiondetection=True, drag={"x": 1, "y": 0, "z": 1})
    definition = particles.fake.definition
    assert definition["collisiondetection"] is True
    assert definition["drag"] == {"x": 1, "y": 0, "z": 1}


def test_extra_may_not_say_what_a_parameter_already_says(particles: Particles):
    with pytest.raises(ValueError) as exc:
        particles.spawn(Point(0, 0, 0), exptime=3)
    assert "life" in str(exc.value)


# --- input it should not accept -------------------------------------------------


def test_a_place_is_a_point(particles: Particles):
    with pytest.raises(TypeError) as exc:
        particles.spawn((10, 20, 30))
    assert "Point" in str(exc.value)


def test_glow_says_its_range(particles: Particles):
    with pytest.raises(ValueError) as exc:
        particles.spawn(Point(0, 0, 0), glow=20)
    assert "14" in str(exc.value)


def test_no_particles_at_all_is_not_a_burst(particles: Particles):
    with pytest.raises(ValueError):
        particles.spawn(Point(0, 0, 0), amount=0)


def test_time_cannot_run_backwards(particles: Particles):
    with pytest.raises(ValueError):
        particles.spawn(Point(0, 0, 0), time=-1)


def test_a_word_is_not_a_size(particles: Particles):
    with pytest.raises(TypeError) as exc:
        particles.spawn(Point(0, 0, 0), size="big")
    assert "size" in str(exc.value)


def test_a_transparent_colour_is_refused(particles: Particles):
    """Luanti's own note on [colorize: alpha in the colour is undefined behaviour."""
    with pytest.raises(ValueError) as exc:
        particles.spawn(Point(0, 0, 0), color="#ffcc0080")
    assert "glow" in str(exc.value)


def test_a_texture_is_a_name(particles: Particles):
    with pytest.raises(TypeError) as exc:
        particles.spawn(Point(0, 0, 0), texture=42)
    assert SPARK in str(exc.value)


def test_a_number_is_not_a_player(particles: Particles):
    with pytest.raises(TypeError) as exc:
        particles.spawn(Point(0, 0, 0), player=7)
    assert "lt.players" in str(exc.value)


def test_nothing_reaches_the_server_after_a_refusal(particles: Particles):
    with pytest.raises(ValueError):
        particles.spawn(Point(0, 0, 0), glow=20)
    assert particles.fake.calls == []


# --- stopping again -------------------------------------------------------------


def test_every_spawner_gets_its_own_key(particles: Particles):
    first = particles.spawn(Point(0, 0, 0))
    second = particles.spawn(Point(0, 0, 0))
    assert first.key != second.key
    assert first.key in particles.fake.calls[0]


def test_stop_deletes_the_one_it_started(particles: Particles):
    spawner = particles.spawn(Point(0, 0, 0))
    spawner.stop()
    last = particles.fake.calls[-1]
    assert "delete_particlespawner" in last
    assert spawner.key in last


def test_stop_all_walks_the_whole_table(particles: Particles):
    particles.spawn(Point(0, 0, 0))
    particles.stop_all()
    last = particles.fake.calls[-1]
    assert "pairs(miney_spawners)" in last
    assert "miney_spawners = {}" in last


def test_a_with_block_stops_on_the_way_out(particles: Particles):
    with particles.spawn(Point(0, 0, 0), time=0) as smoke:
        assert "delete_particlespawner" not in particles.fake.calls[-1]
    assert smoke.key in particles.fake.calls[-1]


# --- how it talks ---------------------------------------------------------------


def test_nothing_here_waits_for_the_server(particles: Particles):
    """A for loop of bursts should cost no server steps at all."""
    particles.spawn(Point(0, 0, 0)).stop()
    particles.stop_all()
    assert particles.fake.waits == [False, False, False]


def test_it_says_which_spawner_it_is(particles: Particles):
    assert repr(particles.spawn(Point(0, 0, 0))) == '<Luanti ParticleSpawner "spawner-1">'
    assert repr(particles) == "<Luanti Particles>"
