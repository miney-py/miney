"""
Assets against a fake server: the ``miney_assets`` half of the mod, in Python.
"""
import hashlib
import io
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import miney.assets
from miney.assets import Assets, MAX_UPLOAD
from miney.exceptions import AssetError, AssetTimeout, PlayerOffline
from miney.lua import Lua


PNG = b"\x89PNG\r\n\x1a\n" + b"pretend this is a picture"
JPEG = b"\xff\xd8\xff\xe0" + b"pretend this is a photo"
OGG = b"OggS\x00\x02" + b"pretend this is a fanfare"

_PUT = re.compile(r'^return miney_assets\.put\("([^"]*)", "([^"]*)", (\{.*\})\)$')


class FakeAssets:
    """
    The mod side, as far as ``Assets`` can tell.

    Only the five calls Python makes ever arrive, so they are matched rather than
    parsed. ``opts`` stays the raw Lua table text - the tests read it as a string,
    which is also how a person would read it in a log.
    """

    def __init__(self, textures=None, sounds=None, ready_after=0, answer=None):
        self.calls: list[str] = []
        self.puts: list[tuple[str, str, str]] = []
        self.ready_calls = 0
        self.removed: list[str] = []
        self.cleared = 0
        self._textures = textures or {}
        self._sounds = sounds or {}
        #: How many ``ready()`` polls answer no before one answers yes.
        self.ready_after = ready_after
        #: An answer to give ``put`` instead of the successful one.
        self.answer = answer

    def run(self, code: str):
        self.calls.append(code)

        match = _PUT.match(code)
        if match:
            name, data, opts = match.groups()
            self.puts.append((name, data, opts))
            return self.answer or {"name": name}

        if code.startswith("return miney_assets.ready("):
            self.ready_calls += 1
            return self.ready_calls > self.ready_after

        if code == "return miney_assets.textures()":
            return {mod: list(files) for mod, files in self._textures.items()}

        if code == "return miney_assets.sounds()":
            return {mod: list(names) for mod, names in self._sounds.items()}

        if code == "return miney_assets.list()":
            return [name for name, _, _ in self.puts]

        if code.startswith("return miney_assets.remove("):
            self.removed.append(code[len('return miney_assets.remove("'):-2])
            return True

        if code == "return miney_assets.clear()":
            self.cleared += 1
            return len(self.puts)

        raise AssertionError(f"unexpected Lua: {code!r}")


def make_assets(**kwargs) -> Assets:
    luanti = MagicMock()
    fake = FakeAssets(**kwargs)
    luanti.lua = MagicMock()
    luanti.lua.run.side_effect = fake.run
    luanti.lua.dumps.side_effect = Lua.dumps.__get__(luanti.lua)
    assets = Assets(luanti)
    assets.fake = fake
    return assets


@pytest.fixture
def assets() -> Assets:
    return make_assets()


@pytest.fixture(autouse=True)
def _fast_polling(monkeypatch):
    """Nobody waits 200 ms per poll in a test."""
    monkeypatch.setattr(miney.assets, "POLL_INTERVAL", 0.001)


# --- what upload() accepts ------------------------------------------------------


def test_png_bytes_are_recognised_by_their_magic_bytes(assets: Assets):
    assert assets.upload(PNG).endswith(".png")


def test_jpeg_bytes_are_recognised_by_their_magic_bytes(assets: Assets):
    assert assets.upload(JPEG).endswith(".jpg")


def test_a_path_takes_its_format_from_the_suffix(assets: Assets, tmp_path: Path):
    picture = tmp_path / "cat.JPEG"
    picture.write_bytes(PNG)  # the suffix decides, not the content
    assert assets.upload(picture).endswith(".jpg")


def test_ogg_bytes_are_recognised_by_their_magic_bytes(assets: Assets):
    """A sound goes up the same way a picture does, so lt.sound.play() can use it."""
    assert assets.upload(OGG).endswith(".ogg")


def test_an_ogg_file_takes_its_format_from_the_suffix(assets: Assets, tmp_path: Path):
    song = tmp_path / "fanfare.ogg"
    song.write_bytes(OGG)
    assert assets.upload(song).endswith(".ogg")


def test_an_unsupported_format_names_what_works(assets: Assets):
    with pytest.raises(ValueError) as exc:
        assets.upload(b"GIF89a" + b"x" * 20)
    message = str(exc.value)
    assert "PNG" in message and "JPEG" in message and "Ogg" in message


def test_a_string_is_a_name_and_not_a_file(assets: Assets):
    """The one call a beginner tries first, and the one Miney must not guess at."""
    with pytest.raises(TypeError) as exc:
        assets.upload("cat.png")
    assert 'Path("cat.png")' in str(exc.value)


def test_a_figure_is_read_through_savefig_without_matplotlib(assets: Assets):
    class Figure:
        def savefig(self, buffer, format=None, **kwargs):
            assert format == "png"
            buffer.write(PNG)

    assert assets.upload(Figure()).endswith(".png")


def test_an_image_is_read_through_save_without_pillow(assets: Assets):
    class Image:
        def save(self, buffer, format=None, **kwargs):
            assert format == "PNG"
            buffer.write(PNG)

    assert assets.upload(Image()).endswith(".png")


def test_a_file_object_is_read(assets: Assets):
    assert assets.upload(io.BytesIO(PNG)).endswith(".png")


# --- the name -------------------------------------------------------------------


def test_the_name_is_a_hash_of_the_content(assets: Assets):
    digest = hashlib.sha256(PNG).hexdigest()[:12]
    assert assets.upload(PNG) == f"miney_{digest}.png"


def test_the_same_picture_twice_keeps_the_same_name(assets: Assets):
    assert assets.upload(PNG) == assets.upload(PNG)


def test_a_changed_picture_is_a_different_name(assets: Assets):
    assert assets.upload(PNG) != assets.upload(PNG + b"!")


def test_a_given_name_is_used_as_it_is(assets: Assets):
    assert assets.upload(PNG, name="logo.png") == "logo.png"


@pytest.mark.parametrize("name", ["../escape.png", "sub/dir.png", "logo", "logo.gif"])
def test_a_name_that_cannot_become_a_file_is_refused(assets: Assets, name: str):
    """With keep=True the name becomes a path on the server's disk."""
    with pytest.raises(ValueError):
        assets.upload(PNG, name=name)
    assert not assets.fake.puts


# --- who sees it, and for how long ----------------------------------------------


def test_a_plain_upload_is_for_everybody_until_the_server_stops(assets: Assets):
    assets.upload(PNG)
    _, _, opts = assets.fake.puts[0]
    assert opts == "{}"


def test_player_makes_it_that_players_own(assets: Assets):
    player = MagicMock()
    player.name = "Steve"
    assets.upload(PNG, player=player)
    _, _, opts = assets.fake.puts[0]
    assert 'player="Steve"' in opts


def test_a_player_name_works_as_well_as_a_player(assets: Assets):
    assets.upload(PNG, player="Steve")
    assert 'player="Steve"' in assets.fake.puts[0][2]


def test_keep_asks_the_mod_to_write_it_to_disk(assets: Assets):
    assets.upload(PNG, keep=True)
    assert "keep=true" in assets.fake.puts[0][2]


def test_an_offline_player_raises_player_offline():
    assets = make_assets(
        answer={"error": "'Steve' is not online.", "kind": "offline"}
    )
    with pytest.raises(PlayerOffline):
        assets.upload(PNG, player="Steve")


# --- the limits -----------------------------------------------------------------


def test_a_picture_over_the_limit_is_refused_before_it_is_sent(assets: Assets):
    too_big = PNG + b"x" * MAX_UPLOAD
    with pytest.raises(ValueError) as exc:
        assets.upload(too_big)
    assert str(MAX_UPLOAD) in str(exc.value)
    assert not assets.fake.puts  # nothing went over the wire


def test_the_mod_refusing_on_size_is_a_value_error():
    assets = make_assets(
        answer={"error": "The kept assets are full. Use lt.assets.clear().",
                "kind": "limit"}
    )
    with pytest.raises(ValueError) as exc:
        assets.upload(PNG, keep=True)
    assert "lt.assets.clear()" in str(exc.value)


def test_the_mod_refusing_otherwise_is_an_asset_error():
    assets = make_assets(answer={"error": "the engine said no"})
    with pytest.raises(AssetError) as exc:
        assets.upload(PNG)
    assert "the engine said no" in str(exc.value)


# --- waiting --------------------------------------------------------------------


def test_upload_waits_until_the_client_really_has_it():
    """
    The whole point of blocking: the next line names this texture, and a client that
    does not have it yet draws nothing at all.
    """
    assets = make_assets(ready_after=2)
    assets.upload(PNG)
    assert assets.fake.ready_calls == 3


def test_a_client_that_never_confirms_raises_asset_timeout():
    assets = make_assets(ready_after=999)
    with pytest.raises(AssetTimeout) as exc:
        assets.upload(PNG, timeout=0)
    assert "smaller" in str(exc.value)


def test_waiting_asks_about_the_one_player_it_was_sent_to():
    assets = make_assets()
    assets.upload(PNG, player="Steve")
    ready = [c for c in assets.fake.calls if c.startswith("return miney_assets.ready(")]
    assert ready[0].endswith('"Steve")')


# --- list, remove, clear --------------------------------------------------------


def test_list_remove_and_clear_reach_the_mod(assets: Assets):
    name = assets.upload(PNG)
    assert assets.list() == [name]
    assets.remove(name)
    assert assets.fake.removed == [name]
    assets.clear()
    assert assets.fake.cleared == 1


# --- textures -------------------------------------------------------------------


TEXTURES = {
    "default": ["default_dirt.png", "default_stone.png"],
    "mcl_core": ["mcl_core_sand.png"],
}


def test_textures_are_not_read_until_something_asks():
    """VoxeLibre ships thousands of them; no connection pays for that list unasked."""
    assets = make_assets(textures=TEXTURES)
    assert assets.fake.calls == []

    assets.textures
    assert assets.fake.calls == ["return miney_assets.textures()"]


def test_textures_are_read_once_and_kept():
    assets = make_assets(textures=TEXTURES)
    assets.textures.default.dirt
    assets.textures.mcl_core.sand
    assert assets.fake.calls.count("return miney_assets.textures()") == 1


def test_textures_are_grouped_by_mod_with_the_prefix_stripped():
    assets = make_assets(textures=TEXTURES)
    assert assets.textures.default.dirt == "default_dirt.png"
    assert assets.textures.mcl_core.sand == "mcl_core_sand.png"


def test_every_texture_is_in_the_flat_list():
    assets = make_assets(textures=TEXTURES)
    assert sorted(assets.textures) == [
        "default_dirt.png", "default_stone.png", "mcl_core_sand.png",
    ]
    assert len(assets.textures) == 3


# --- sounds ---------------------------------------------------------------------


SOUNDS = {
    "default": ["default_dig_stone", "default_place_node"],
    "mcl_portals": ["mcl_portals_open"],
}


def test_sounds_are_not_read_until_something_asks():
    assets = make_assets(sounds=SOUNDS)
    assert assets.fake.calls == []

    assets.sounds
    assert assets.fake.calls == ["return miney_assets.sounds()"]


def test_sounds_are_read_once_and_kept():
    assets = make_assets(sounds=SOUNDS)
    assets.sounds.default.dig_stone
    assets.sounds.mcl_portals.open
    assert assets.fake.calls.count("return miney_assets.sounds()") == 1


def test_sounds_are_grouped_by_mod_with_the_prefix_stripped():
    assets = make_assets(sounds=SOUNDS)
    assert assets.sounds.default.dig_stone == "default_dig_stone"
    assert assets.sounds.mcl_portals.open == "mcl_portals_open"


def test_sounds_and_textures_do_not_share_their_flat_list():
    """Both are read through the same Assets, and either one counting both would lie."""
    assets = make_assets(textures=TEXTURES, sounds=SOUNDS)
    assert len(assets.textures) == 3
    assert len(assets.sounds) == 3
    assert sorted(assets.sounds) == [
        "default_dig_stone", "default_place_node", "mcl_portals_open",
    ]


def test_a_server_with_no_sounds_answers_with_nothing():
    """An empty Lua table arrives as an empty list, not as an empty object."""
    assets = make_assets()
    assets.fake._sounds = {}
    assert list(assets.sounds) == []


def test_repr_says_what_it_is(assets: Assets):
    assert repr(assets) == "<Luanti Assets>"
