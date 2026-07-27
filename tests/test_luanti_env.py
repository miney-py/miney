from __future__ import annotations
import argparse
from pathlib import Path

import pytest

import miney.cli as cli_module
import miney.luanti as luanti_module
from miney.channel import Beacon
from miney.env import manage
from miney.env.paths import EnvPaths
from miney.env.state import WorldState, save_state
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

    The constructor does more than attach: it builds Callback, Lua, Chat and Nodes and
    runs Lua to cache the tool list. Every one of those has to be stubbed or the
    constructor never returns.

    Yields ``(running, attached)``: put a beacon in ``running`` to say a server is up,
    and read ``attached`` to see which channel directory Miney went for.
    """
    running: list[Beacon] = []
    attached: list[Path] = []

    class FakeChannel:
        mod_api = 7
        connected = True

        def __init__(self, directory, timeout=10.0):
            self.directory = Path(directory)
            attached.append(self.directory)

        def add_listener(self, listener):
            return None

        def send(self, fields):
            return True

        def answered(self):
            return None

        def timeout_hint(self):
            return "hint"

        def close(self):
            return None

    class FakeLua:
        def __init__(self, *args, **kwargs):
            pass

        def run(self, code, timeout=10, execution_id=None, wait=True):
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

    monkeypatch.setattr(luanti_module, "find_beacons",
                        lambda luanti_dir=None: sorted(running, key=lambda b: -b.started))
    monkeypatch.setattr(luanti_module, "FileChannel", FakeChannel)
    monkeypatch.setattr(luanti_module, "Lua", FakeLua)
    monkeypatch.setattr(luanti_module, "Callback", FakeCallback)
    monkeypatch.setattr(luanti_module, "Chat", FakeSimple)
    monkeypatch.setattr(luanti_module, "Nodes", FakeSimple)
    monkeypatch.setattr(luanti_module, "ToolIterable", FakeSimple)
    return running, attached


def a_server_on(world_dir: Path, started: int = 100) -> Beacon:
    """
    A beacon for a world, as a running server would have left it.

    :param world_dir: The world directory the server is running.
    :param started: Unix time it came up, which decides the order.
    """
    return Beacon(
        directory=world_dir.parent / f"channel-{world_dir.name}",
        mod_api=8,
        engine="5.16.1",
        world=str(world_dir),
        world_name=world_dir.name,
        singleplayer=False,
        started=started,
    )


def test_attaches_to_the_only_server_that_is_running(tmp_path, no_real_connection):
    running, attached = no_real_connection
    running.append(a_server_on(tmp_path / "worlds" / "minetest_game"))

    luanti_module.Luanti(autostart=False)

    assert attached == [tmp_path / "worlds" / "channel-minetest_game"]


def test_a_world_the_user_started_themselves_is_found(tmp_path, monkeypatch,
                                                      no_real_connection):
    """
    The point of the whole transport: no project, no environment, nothing configured.

    Somebody opened a singleplayer world from the Luanti menu, and that is the world
    a script written next to it means.
    """
    monkeypatch.chdir(tmp_path)
    running, attached = no_real_connection
    running.append(a_server_on(tmp_path / "Luanti" / "worlds" / "mine"))

    luanti_module.Luanti()

    assert attached and attached[0].name == "channel-mine"


def test_several_running_servers_require_naming_one(tmp_path, no_real_connection):
    running, _ = no_real_connection
    running.append(a_server_on(tmp_path / "alpha", started=1))
    running.append(a_server_on(tmp_path / "beta", started=2))

    with pytest.raises(MineyRunError) as error:
        luanti_module.Luanti(autostart=False)

    message = str(error.value)
    assert "alpha" in message and "beta" in message
    assert 'miney.Luanti(world="beta")' in message


def test_a_named_world_picks_its_server(tmp_path, no_real_connection):
    running, attached = no_real_connection
    running.append(a_server_on(tmp_path / "alpha", started=1))
    running.append(a_server_on(tmp_path / "beta", started=2))

    luanti_module.Luanti(world="alpha", autostart=False)

    assert attached == [tmp_path / "channel-alpha"]


def test_a_named_world_that_is_not_running_says_what_is(tmp_path, no_real_connection):
    running, _ = no_real_connection
    running.append(a_server_on(tmp_path / "alpha"))

    with pytest.raises(MineyRunError) as error:
        luanti_module.Luanti(world="beta", autostart=False)

    assert "'beta'" in str(error.value)
    assert "'alpha'" in str(error.value)


def test_no_server_and_no_environment_says_how_to_get_one(tmp_path, monkeypatch,
                                                          no_real_connection):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(MineyRunError) as error:
        luanti_module.Luanti()

    message = str(error.value)
    assert "miney start" in message
    assert "miney" in message.lower()


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


def test_autostart_disabled_reports_how_to_start(tmp_path, monkeypatch,
                                                 no_real_connection):
    monkeypatch.chdir(tmp_path)
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("w"), WorldState("w", "minetest_game", 30000))
    monkeypatch.setattr(manage, "is_server_up", lambda state: False)

    with pytest.raises(MineyRunError) as error:
        luanti_module.Luanti(autostart=False)

    assert "miney start" in str(error.value)


def test_a_running_world_without_a_channel_says_the_mod_is_too_old(tmp_path, monkeypatch,
                                                                   no_real_connection):
    """
    The server is up and answering on its port, but it left no beacon.

    That can only mean its 'miney' mod is missing or from before the file channel, and
    saying so beats waiting for a timeout that names nothing.
    """
    monkeypatch.chdir(tmp_path)
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("w"), WorldState("w", "minetest_game", 30000, server_pid=1))
    monkeypatch.setattr(manage, "is_server_up", lambda state: True)

    with pytest.raises(MineyRunError) as error:
        luanti_module.Luanti()

    assert "miney upgrade" in str(error.value)


def test_failed_autostart_raises_instead_of_attaching(tmp_path, monkeypatch,
                                                      no_real_connection):
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


def test_successful_autostart_attaches_to_the_world_it_started(tmp_path, monkeypatch,
                                                               no_real_connection):
    monkeypatch.chdir(tmp_path)
    running, attached = no_real_connection
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("w"), WorldState("w", "minetest_game", 30000))
    monkeypatch.setattr(manage, "is_server_up", lambda state: False)

    def fake_start(paths, world, game, **kwargs):
        state = WorldState(world, game, 30555, server_pid=4242, client_pid=4243)
        save_state(paths.state_file(world), state)
        # What a server does once its mod has loaded.
        running.append(a_server_on(paths.world_dir(world)))
        return manage.StartResult(state=state)

    monkeypatch.setattr(manage, "start", fake_start)

    luanti_module.Luanti()  # autostart defaults to True

    assert attached == [paths.worlds_dir / "channel-w"]


def test_autostart_does_not_go_through_the_command_line(tmp_path, monkeypatch,
                                                        no_real_connection):
    """
    The library must not route through argparse: that inherited the command's
    printing, its exit-code-as-error-channel and all of its side effects.
    """
    monkeypatch.chdir(tmp_path)
    running, _ = no_real_connection
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("w"), WorldState("w", "mineclone2", 30000))
    monkeypatch.setattr(manage, "is_server_up", lambda state: False)

    def refuse(argv=None):
        raise AssertionError("Luanti() went through the miney command line")

    monkeypatch.setattr(cli_module, "main", refuse)
    calls = []

    def fake_start(paths, world, game, **kwargs):
        calls.append((world, game))
        running.append(a_server_on(paths.world_dir(world)))
        return manage.StartResult(state=WorldState(world, game, 30000, server_pid=4242))

    monkeypatch.setattr(manage, "start", fake_start)

    luanti_module.Luanti()

    assert calls == [("w", "mineclone2")]


def test_a_running_world_is_not_started_again(tmp_path, monkeypatch, no_real_connection):
    monkeypatch.chdir(tmp_path)
    running, attached = no_real_connection
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("w"), WorldState("w", "minetest_game", 30007, server_pid=1))
    running.append(a_server_on(paths.world_dir("w")))

    def refuse(*args, **kwargs):
        raise AssertionError("started a world that was already up")

    monkeypatch.setattr(manage, "start", refuse)

    luanti_module.Luanti()

    assert attached == [paths.worlds_dir / "channel-w"]


def test_a_beacon_from_a_server_that_is_gone_falls_through_to_autostart(
    tmp_path, monkeypatch, no_real_connection
):
    """
    A killed server leaves its beacon behind and there is no pid in it to check.

    So the only way to tell a live server from a corpse is to ask one and see, and
    Miney has to carry on sensibly when nothing answers.
    """
    monkeypatch.chdir(tmp_path)
    running, attached = no_real_connection
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("w"), WorldState("w", "minetest_game", 30000))
    monkeypatch.setattr(manage, "is_server_up", lambda state: False)

    stale = a_server_on(tmp_path / "gone", started=1)
    running.append(stale)

    real = luanti_module.FileChannel

    class RefusesTheStaleOne(real):
        def __init__(self, directory, timeout=10.0):
            if Path(directory) == stale.directory:
                raise MineyRunError("did not answer")
            super().__init__(directory, timeout)

    monkeypatch.setattr(luanti_module, "FileChannel", RefusesTheStaleOne)

    def fake_start(paths, world, game, **kwargs):
        running.append(a_server_on(paths.world_dir(world), started=9))
        return manage.StartResult(state=WorldState(world, game, 30000, server_pid=1))

    monkeypatch.setattr(manage, "start", fake_start)

    luanti_module.Luanti()

    assert attached == [paths.worlds_dir / "channel-w"]
