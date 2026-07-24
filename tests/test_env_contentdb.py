"""Tests for miney.env.contentdb."""
import io
import zipfile
from pathlib import Path

import pytest

from miney.env.contentdb import (
    GAME_PACKAGES,
    default_world_name,
    game_label,
    install_game,
    package_url,
)
from miney.exceptions import MineyRunError


def test_game_label_names_voxelibre_with_its_old_id():
    # VoxeLibre kept the game id "mineclone2"; show the new name and the still-needed id.
    assert game_label("mineclone2") == "VoxeLibre (mineclone2)"


def test_default_world_name_uses_the_voxelibre_brand():
    # A world made for VoxeLibre is called "VoxeLibre", not the raw id "mineclone2".
    assert default_world_name("mineclone2") == "VoxeLibre"


def test_default_world_name_falls_back_to_the_id():
    assert default_world_name("minetest_game") == "minetest_game"


def test_game_label_of_minetest_game():
    assert game_label("minetest_game") == "Minetest Game"


def test_game_label_falls_back_to_the_id():
    assert game_label("some_other_game") == "some_other_game"


def _game_zip(root: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{root}/game.conf", "title = Test\n")
        archive.writestr(f"{root}/mods/default/init.lua", "-- nothing\n")
    return buffer.getvalue()


def test_package_url_points_at_luanti_not_minetest():
    # content.minetest.net is the old host; the prototype this replaces still used it.
    url = package_url("Luanti", "minetest_game")
    assert url == "https://content.luanti.org/packages/Luanti/minetest_game/download/"


def test_install_game_extracts_under_the_game_id(tmp_path: Path):
    requested = []

    def fetch(url: str) -> bytes:
        requested.append(url)
        return _game_zip("minetest_game")

    result = install_game("minetest_game", tmp_path, fetch=fetch)
    assert result == tmp_path / "minetest_game"
    assert (result / "game.conf").is_file()
    assert requested == ["https://content.luanti.org/packages/Luanti/minetest_game/download/"]


def test_install_game_renames_a_differently_named_archive_root(tmp_path: Path):
    # Luanti takes the game id from the directory name, so the id has to win.
    result = install_game("mineclone2", tmp_path, fetch=lambda url: _game_zip("VoxeLibre"))
    assert result == tmp_path / "mineclone2"
    assert (result / "game.conf").is_file()


def test_install_game_names_the_known_games_in_its_error(tmp_path: Path):
    with pytest.raises(MineyRunError, match="minetest_game"):
        install_game("no_such_game", tmp_path, fetch=lambda url: b"")


def test_the_default_game_is_known():
    assert "minetest_game" in GAME_PACKAGES
    assert GAME_PACKAGES["minetest_game"] == ("Luanti", "minetest_game")


def test_voxelibre_is_known_under_its_game_id():
    assert GAME_PACKAGES["mineclone2"] == ("Wuzzy", "mineclone2")
