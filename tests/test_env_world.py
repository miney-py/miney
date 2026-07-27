from __future__ import annotations
from pathlib import Path

import pytest

from miney.env.paths import EnvPaths
from miney.env.world import (
    DEFAULT_GAME,
    derive_player_name,
    ensure_client_password,
    install_mod,
    mod_fingerprint,
    read_world_gameid,
    write_config,
    write_world_mt,
)


def test_world_mt_records_the_game(tmp_path: Path):
    write_world_mt(tmp_path, "mineclone2")
    text = (tmp_path / "world.mt").read_text(encoding="utf-8")
    assert "gameid = mineclone2" in text


def test_world_mt_does_not_need_a_load_mod_line(tmp_path: Path):
    # The mod lives in worldmods/, which Luanti loads unconditionally.
    write_world_mt(tmp_path, DEFAULT_GAME)
    assert "load_mod_" not in (tmp_path / "world.mt").read_text(encoding="utf-8")


def test_world_mt_sets_every_backend_to_sqlite3(tmp_path: Path):
    # Luanti warns that each file-based backend it falls back to "may be removed in a
    # future release". Verified against Luanti 5.16.1: naming only `backend` leaves the
    # other three on the deprecated file backend.
    write_world_mt(tmp_path, DEFAULT_GAME)
    text = (tmp_path / "world.mt").read_text(encoding="utf-8")
    for key in ("backend", "player_backend", "auth_backend", "mod_storage_backend"):
        assert f"{key} = sqlite3" in text


def test_read_world_gameid_roundtrips(tmp_path: Path):
    write_world_mt(tmp_path, "mineclone2")
    assert read_world_gameid(tmp_path) == "mineclone2"


def test_read_world_gameid_returns_none_for_a_new_directory(tmp_path: Path):
    assert read_world_gameid(tmp_path) is None


def test_config_grants_the_miney_privilege(tmp_path: Path):
    target = tmp_path / "luanti.conf"
    write_config(target)
    text = target.read_text(encoding="utf-8")
    privs = [line for line in text.splitlines() if line.startswith("default_privs")][0]
    assert "miney" in privs
    assert "interact" in privs
    assert "shout" in privs


def test_config_binds_the_server_to_loopback_only(tmp_path: Path):
    # Off 127.0.0.1 the server pops a Windows firewall dialog and exposes its port to
    # the local network, neither of which a single-machine learning server wants.
    target = tmp_path / "luanti.conf"
    write_config(target)
    assert "bind_address = 127.0.0.1" in target.read_text(encoding="utf-8").splitlines()


def test_config_shortens_the_server_step(tmp_path: Path):
    # Every Miney command is answered on the step after the one that picked it up, so
    # the default 0.09 is the whole of the latency in the REPL.
    target = tmp_path / "luanti.conf"
    write_config(target)
    assert "dedicated_server_step = 0.03" in target.read_text(encoding="utf-8").splitlines()


def test_config_creates_parent_directories(tmp_path: Path):
    target = tmp_path / "deep" / "luanti.conf"
    write_config(target)
    assert target.is_file()


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Netzvamp", "Netzvamp"),
        ("Robert Lieback", "RobertLieback"),
        ("some.user", "someuser"),
        ("ä", "player"),
        ("", "player"),
        ("a" * 40, "a" * 20),
    ],
)
def test_derive_player_name(raw: str, expected: str):
    assert derive_player_name(raw) == expected


def test_derive_player_name_avoids_the_bot_account():
    assert derive_player_name("miney") == "miney1"


def test_client_password_is_created_once_and_reused(tmp_path: Path):
    target = tmp_path / "client.pw"

    first = ensure_client_password(target, generator=lambda: "generated")
    second = ensure_client_password(target, generator=lambda: "different")

    assert first == "generated"
    assert second == "generated"
    assert target.read_text(encoding="utf-8") == "generated"


def test_client_password_has_no_trailing_newline(tmp_path: Path):
    target = tmp_path / "client.pw"
    ensure_client_password(target, generator=lambda: "secret")
    assert target.read_bytes() == b"secret"


def test_install_mod_copies_into_worldmods(tmp_path: Path):
    source = tmp_path / "src" / "miney"
    source.mkdir(parents=True)
    (source / "mod.conf").write_text("name = miney\n")
    (source / "init.lua").write_text("-- mod\n")
    world = tmp_path / "world"

    installed = install_mod(world, source)

    assert installed == world / "worldmods" / "miney"
    assert (installed / "mod.conf").is_file()
    assert (installed / "init.lua").is_file()


def test_install_mod_replaces_an_older_copy(tmp_path: Path):
    source = tmp_path / "src" / "miney"
    source.mkdir(parents=True)
    (source / "mod.conf").write_text("name = miney\n")
    world = tmp_path / "world"
    stale = world / "worldmods" / "miney"
    stale.mkdir(parents=True)
    (stale / "leftover.lua").write_text("old\n")

    install_mod(world, source)

    assert not (world / "worldmods" / "miney" / "leftover.lua").exists()
    assert (world / "worldmods" / "miney" / "mod.conf").is_file()


def test_mod_fingerprint_of_a_missing_directory_is_empty(tmp_path: Path):
    assert mod_fingerprint(tmp_path / "not-installed") == ""


def test_mod_fingerprint_matches_a_fresh_copy(tmp_path: Path):
    source = tmp_path / "src" / "miney"
    source.mkdir(parents=True)
    (source / "mod.conf").write_text("name = miney\n")
    (source / "init.lua").write_text("-- mod\n")
    world = tmp_path / "world"

    installed = install_mod(world, source)

    assert mod_fingerprint(installed) == mod_fingerprint(source)


def test_mod_fingerprint_notices_a_changed_file(tmp_path: Path):
    """
    mod.conf carries no version, so only the file contents can tell an upgraded mod
    from the installed one.
    """
    source = tmp_path / "src" / "miney"
    source.mkdir(parents=True)
    (source / "mod.conf").write_text("name = miney\n")
    (source / "init.lua").write_text("-- old\n")
    world = tmp_path / "world"
    installed = install_mod(world, source)

    (source / "init.lua").write_text("-- new\n")

    assert mod_fingerprint(installed) != mod_fingerprint(source)


def test_mod_fingerprint_notices_an_added_file(tmp_path: Path):
    source = tmp_path / "src" / "miney"
    source.mkdir(parents=True)
    (source / "mod.conf").write_text("name = miney\n")
    world = tmp_path / "world"
    installed = install_mod(world, source)

    (source / "extra.lua").write_text("-- new file\n")

    assert mod_fingerprint(installed) != mod_fingerprint(source)


def test_mod_fingerprint_ignores_where_the_directory_lives(tmp_path: Path):
    first = tmp_path / "a" / "miney"
    second = tmp_path / "b" / "miney"
    for directory in (first, second):
        (directory / "sub").mkdir(parents=True)
        (directory / "mod.conf").write_text("name = miney\n")
        (directory / "sub" / "player.lua").write_text("-- p\n")

    assert mod_fingerprint(first) == mod_fingerprint(second)


def test_paths_and_world_generation_fit_together(tmp_path: Path):
    paths = EnvPaths(root=tmp_path / ".miney")
    write_world_mt(paths.world_dir(DEFAULT_GAME), DEFAULT_GAME)
    assert read_world_gameid(paths.world_dir(DEFAULT_GAME)) == DEFAULT_GAME
