from __future__ import annotations
import argparse
from pathlib import Path

import pytest

import miney.cli as cli_module
import miney.luanti as luanti_module
from miney.env import manage
from miney.env.paths import EnvPaths
from miney.env.state import WorldState, load_state, save_state
from miney.exceptions import MineyRunError


@pytest.fixture(autouse=True)
def no_environment_lookup():
    """
    Undo tests/conftest.py's global suppression of ``find_env``.

    This whole module exists to test environment lookup, so it needs the real
    ``miney.luanti.find_env`` (walking upward from the chdir'd ``tmp_path``), not the
    "always None" stub the rest of the suite gets by default.
    """
    return None


@pytest.fixture
def no_real_connection(monkeypatch):
    """
    Replace everything Luanti.__init__ reaches for.

    The constructor does more than connect: it builds Callback, Lua, Chat and Nodes, runs
    Lua to cache the tool list, and tries to make the bot invisible. Every one of those
    has to be stubbed or the constructor never returns.
    """

    class FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.command_handler = None
            self.connection = None

        def connect(self, register: bool = False):
            return None

        def disconnect(self):
            return None

    class FakeLua:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, code, timeout=10, execution_id=None):
            return []

        def dumps(self, data):
            return "{}"

    class FakeCallback:
        def __init__(self, *args, **kwargs):
            pass

        def register(self, *args, **kwargs):
            return "token"

        def shutdown(self):
            return None

    class FakeSimple:
        def __init__(self, *args, **kwargs):
            pass

    monkeypatch.setattr(luanti_module, "LuantiClient", FakeClient)
    monkeypatch.setattr(luanti_module, "Lua", FakeLua)
    monkeypatch.setattr(luanti_module, "Callback", FakeCallback)
    monkeypatch.setattr(luanti_module, "Chat", FakeSimple)
    monkeypatch.setattr(luanti_module, "Nodes", FakeSimple)
    monkeypatch.setattr(luanti_module, "ToolIterable", FakeSimple)
    return None


def test_uses_the_only_world_in_the_environment(tmp_path, monkeypatch, no_real_connection):
    monkeypatch.chdir(tmp_path)
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("minetest_game"),
               WorldState("minetest_game", "minetest_game", 30007, server_pid=1))
    monkeypatch.setattr(manage, "is_server_up", lambda state: True)

    lt = luanti_module.Luanti(autostart=False)

    assert lt.port == 30007


def test_explicit_server_ignores_the_environment(tmp_path, monkeypatch, no_real_connection):
    monkeypatch.chdir(tmp_path)
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("minetest_game"),
               WorldState("minetest_game", "minetest_game", 30007))

    lt = luanti_module.Luanti("elsewhere.example")

    assert lt.server == "elsewhere.example"
    assert lt.port == 30000


def test_several_worlds_require_naming_one(tmp_path, monkeypatch, no_real_connection):
    monkeypatch.chdir(tmp_path)
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("alpha"), WorldState("alpha", "minetest_game", 30000))
    save_state(paths.state_file("beta"), WorldState("beta", "mineclone2", 30001))
    monkeypatch.setattr(manage, "is_server_up", lambda state: False)

    with pytest.raises(MineyRunError) as error:
        luanti_module.Luanti(autostart=False)

    assert "alpha" in str(error.value)
    assert "beta" in str(error.value)


def test_the_running_world_is_the_one_that_is_meant(tmp_path, monkeypatch,
                                                    no_real_connection):
    """
    A second world must not take the answer away from a script that worked yesterday.

    This is the whole point of the rule: a test world, a tutorial world or a world left
    over from an experiment sits on disk beside the one being worked in, and the one
    that is *running* is obviously the one meant.
    """
    monkeypatch.chdir(tmp_path)
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("alpha"), WorldState("alpha", "minetest_game", 30000))
    save_state(paths.state_file("beta"), WorldState("beta", "mineclone2", 30001))
    monkeypatch.setattr(manage, "is_server_up", lambda state: state.name == "beta")

    lt = luanti_module.Luanti(autostart=False)

    assert lt.port == 30001


def test_a_bare_start_reuses_a_world_instead_of_inventing_one(tmp_path, monkeypatch):
    """
    'miney start' with several worlds and none running must not create a new one.

    It used to fall through to the world named after the default game, which with two
    worlds already there meant a *third* one: a first start, a full map generation, and
    minutes of waiting for a world nobody asked for.
    """
    monkeypatch.chdir(tmp_path)
    paths = EnvPaths(root=tmp_path / ".miney")
    for name, game, port in (("alpha", "minetest_game", 30000),
                             ("beta", "mineclone2", 30001)):
        save_state(paths.state_file(name), WorldState(name, game, port))
        (paths.world_dir(name)).mkdir(parents=True, exist_ok=True)
        (paths.world_dir(name) / "world.mt").write_text(f"gameid = {game}\n",
                                                        encoding="utf-8")
    monkeypatch.setattr(manage, "is_server_up", lambda state: False)
    # 'beta' was worked in last.
    later = paths.state_file("alpha").stat().st_mtime + 60
    import os
    os.utime(paths.state_file("beta"), (later, later))

    args = argparse.Namespace(world=None, game=None)
    world, game = cli_module._resolve_world_and_game(paths, args)

    assert (world, game) == ("beta", "mineclone2")


def test_a_named_port_picks_the_world_on_it(tmp_path, monkeypatch, no_real_connection):
    monkeypatch.chdir(tmp_path)
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("alpha"), WorldState("alpha", "minetest_game", 30000))
    save_state(paths.state_file("beta"), WorldState("beta", "mineclone2", 30001))
    monkeypatch.setattr(manage, "is_server_up", lambda state: True)

    lt = luanti_module.Luanti(port=30001, autostart=False)

    assert lt.port == 30001


def test_several_running_worlds_are_all_named_in_the_error(tmp_path, monkeypatch,
                                                           no_real_connection):
    monkeypatch.chdir(tmp_path)
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("alpha"), WorldState("alpha", "minetest_game", 30000))
    save_state(paths.state_file("beta"), WorldState("beta", "mineclone2", 30001))
    monkeypatch.setattr(manage, "is_server_up", lambda state: True)

    with pytest.raises(MineyRunError) as error:
        luanti_module.Luanti(autostart=False)

    message = str(error.value)
    assert "running" in message
    assert "alpha" in message and "beta" in message


def test_the_error_suggests_the_world_used_last(tmp_path, monkeypatch,
                                                no_real_connection):
    """Not the first one alphabetically - that is the throwaway world often enough."""
    monkeypatch.chdir(tmp_path)
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("alpha"), WorldState("alpha", "minetest_game", 30000))
    save_state(paths.state_file("beta"), WorldState("beta", "mineclone2", 30001))
    monkeypatch.setattr(manage, "is_server_up", lambda state: False)
    # 'beta' was written a minute later than 'alpha'.
    import os
    later = paths.state_file("alpha").stat().st_mtime + 60
    os.utime(paths.state_file("beta"), (later, later))

    with pytest.raises(MineyRunError) as error:
        luanti_module.Luanti(autostart=False)

    assert 'miney.Luanti(world="beta")' in str(error.value)
    assert "miney start --world beta" in str(error.value)


def test_named_world_is_selected(tmp_path, monkeypatch, no_real_connection):
    monkeypatch.chdir(tmp_path)
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("alpha"), WorldState("alpha", "minetest_game", 30000))
    save_state(paths.state_file("beta"), WorldState("beta", "mineclone2", 30001))
    monkeypatch.setattr(manage, "is_server_up", lambda state: True)

    lt = luanti_module.Luanti(world="beta", autostart=False)

    assert lt.port == 30001


def test_autostart_disabled_reports_how_to_start(tmp_path, monkeypatch, no_real_connection):
    monkeypatch.chdir(tmp_path)
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("w"), WorldState("w", "minetest_game", 30000))
    monkeypatch.setattr(manage, "is_server_up", lambda state: False)

    with pytest.raises(MineyRunError) as error:
        luanti_module.Luanti(autostart=False)

    assert "miney start" in str(error.value)


def test_failed_autostart_raises_instead_of_connecting(tmp_path, monkeypatch, no_real_connection):
    monkeypatch.chdir(tmp_path)
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("w"), WorldState("w", "minetest_game", 30000))
    monkeypatch.setattr(manage, "is_server_up", lambda state: False)

    def fail_to_start(paths, world, game, **kwargs):
        raise MineyRunError(
            f"The Luanti server for world '{world}' stopped while starting up.\n"
            f"Its log says why: {paths.log_file(world)}"
        )

    monkeypatch.setattr(manage, "start", fail_to_start)

    with pytest.raises(MineyRunError) as error:
        luanti_module.Luanti()  # autostart defaults to True

    assert "w" in str(error.value)
    assert str(paths.log_file("w")) in str(error.value)


def test_successful_autostart_connects_with_the_new_port(tmp_path, monkeypatch, no_real_connection):
    monkeypatch.chdir(tmp_path)
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("w"), WorldState("w", "minetest_game", 30000))
    monkeypatch.setattr(manage, "is_server_up", lambda state: False)

    def fake_start(paths, world, game, **kwargs):
        state = WorldState(world, game, 30555, server_pid=4242, client_pid=4243)
        save_state(paths.state_file(world), state)
        return manage.StartResult(state=state)

    monkeypatch.setattr(manage, "start", fake_start)

    lt = luanti_module.Luanti()  # autostart defaults to True

    assert lt.port == 30555


def test_autostart_does_not_go_through_the_command_line(tmp_path, monkeypatch, no_real_connection):
    """
    The library must not route through argparse: that inherited the command's
    printing, its exit-code-as-error-channel and all of its side effects.
    """
    monkeypatch.chdir(tmp_path)
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("w"), WorldState("w", "mineclone2", 30000))
    monkeypatch.setattr(manage, "is_server_up", lambda state: False)

    def refuse(argv=None):
        raise AssertionError("Luanti() went through the miney command line")

    monkeypatch.setattr(cli_module, "main", refuse)
    calls = []

    def fake_start(paths, world, game, **kwargs):
        calls.append((world, game))
        return manage.StartResult(state=WorldState(world, game, 30000, server_pid=4242))

    monkeypatch.setattr(manage, "start", fake_start)

    luanti_module.Luanti()

    assert calls == [("w", "mineclone2")]


def test_an_explicit_port_still_wins_over_the_worlds_own(tmp_path, monkeypatch, no_real_connection):
    monkeypatch.chdir(tmp_path)
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("w"), WorldState("w", "minetest_game", 30007, server_pid=1))
    monkeypatch.setattr(manage, "is_server_up", lambda state: True)

    lt = luanti_module.Luanti(port=31000)

    assert lt.port == 31000


def test_a_running_world_is_not_started_again(tmp_path, monkeypatch, no_real_connection):
    monkeypatch.chdir(tmp_path)
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("w"), WorldState("w", "minetest_game", 30007, server_pid=1))
    monkeypatch.setattr(manage, "is_server_up", lambda state: True)

    def refuse(*args, **kwargs):
        raise AssertionError("started a world that was already up")

    monkeypatch.setattr(manage, "start", refuse)

    assert luanti_module.Luanti().port == 30007


def test_autostart_does_not_start_a_second_server_next_to_a_foreground_one(
    tmp_path, monkeypatch, no_real_connection
):
    """
    A server run by 'miney start --foreground' records its pid like any other, so the
    real is_server_up sees it. Without that, autostart started a second server on the
    same port and world directory, which died on the port bind and reported itself as
    "stopped while starting up".
    """
    monkeypatch.chdir(tmp_path)
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("w"), WorldState("w", "minetest_game", 30007))
    manage.record_foreground_server(paths, "w", 4711)
    monkeypatch.setattr("miney.env.manage.is_pid_alive", lambda pid: pid == 4711)
    monkeypatch.setattr("miney.env.manage.probe_server", lambda host, port: True)

    def refuse(*args, **kwargs):
        raise AssertionError("started a second server next to the foreground one")

    monkeypatch.setattr(manage, "start", refuse)

    assert luanti_module.Luanti().port == 30007


def test_without_an_environment_nothing_changes(tmp_path, monkeypatch, no_real_connection):
    monkeypatch.chdir(tmp_path)

    lt = luanti_module.Luanti()

    assert lt.server == "127.0.0.1"
    assert lt.port == 30000
