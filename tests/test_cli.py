from __future__ import annotations
from pathlib import Path

import pytest

import miney.cli as cli
from miney.cli import main
from miney.env import manage
from miney.env.discover import LuantiInstall
from miney.env.paths import EnvPaths
from miney.env.state import WorldState, load_state, save_state
from miney.env.world import DEFAULT_GAME

INSTALL = LuantiInstall(launch=["/opt/luanti"], version=(5, 16, 1), source="path")


@pytest.fixture(autouse=True)
def no_environment_lookup():
    """
    Undo tests/conftest.py's global suppression of ``find_env``.

    Every command exercised here goes through ``manage.create_environment`` or
    ``manage.find_environment`` -- both bindings of the same ``find_env`` -- and does
    so for real, against the chdir'd ``tmp_path`` the ``project`` fixture below sets
    up. It needs the real lookup, not the "always None" stub the rest of the suite
    gets by default; ``tmp_path`` lives under the OS temp directory, nowhere near a
    real project, so nothing above it is ever actually found.
    """
    return None


@pytest.fixture
def project(tmp_path, monkeypatch):
    """
    A project directory that is the current directory, with a stubbed Luanti.

    Everything the command line does now happens in ``miney.env.manage``, so that is
    where the stubs go. ``is_server_up`` is stubbed too: the stubbed server never
    really binds a port, and without this the readiness wait would poll it until it
    times out.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("miney.env.manage.discover", lambda paths: INSTALL)
    monkeypatch.setattr("miney.env.manage.is_server_up", lambda state: True)
    monkeypatch.setattr("miney.env.manage.spawn_detached", lambda command, cwd, env=None: 4242)
    monkeypatch.setattr("miney.env.manage.is_pid_alive", lambda pid: False)
    monkeypatch.setattr("miney.env.manage.is_port_free", lambda port, host="127.0.0.1": True)
    # _resolve_port -> find_free_port resolves is_port_free from its own module, not
    # miney.cli's imported reference, so both have to be patched or a real UDP bind
    # against port 30000 leaks into the test on any machine actually running Luanti.
    monkeypatch.setattr(
        "miney.env.process.is_port_free", lambda port, host="127.0.0.1": True
    )
    # A silently skipped upstream lookup, not a real one: describe() and find_luanti()
    # both call it now, and a test suite must never make a real network request.
    monkeypatch.setattr("miney.env.manage.upstream.latest_release", lambda p: None)
    return tmp_path


def test_init_creates_the_environment(project, capsys):
    assert main(["init"]) == 0

    paths = EnvPaths(root=project / ".miney")
    assert (paths.world_dir(DEFAULT_GAME) / "world.mt").is_file()
    assert paths.config_file.is_file()
    assert paths.client_pw.is_file()


def test_init_is_idempotent(project):
    assert main(["init"]) == 0
    assert main(["init"]) == 0


def test_init_refuses_a_different_game_for_an_existing_world(project, capsys):
    main(["init"])

    code = main(["init", "--world", "minetest_game", "--game", "mineclone2"])

    assert code != 0
    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert "mineclone2" in output or "minetest_game" in output


def _answers(*values):
    """A fake input() that returns each given answer in turn."""
    it = iter(values)
    return lambda prompt="": next(it)


def _refuse_input(prompt=""):
    raise AssertionError("asked the user a question when it should not have")


def test_init_prompts_for_the_game_on_a_fresh_project(project, monkeypatch):
    monkeypatch.setattr(cli, "_stdin_is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", _answers("2"))

    assert main(["init"]) == 0

    paths = EnvPaths(root=project / ".miney")
    # A VoxeLibre world is named "VoxeLibre", not after its game id "mineclone2".
    assert (paths.world_dir("VoxeLibre") / "world.mt").is_file()
    assert manage.read_world_gameid(paths.world_dir("VoxeLibre")) == "mineclone2"


def test_init_does_not_prompt_once_a_world_exists(project, monkeypatch):
    main(["init"])  # non-interactive: creates the default world
    monkeypatch.setattr(cli, "_stdin_is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", _refuse_input)

    assert main(["init"]) == 0  # would raise via _refuse_input if it prompted


def test_init_prompts_for_a_new_named_world_even_next_to_an_existing_one(project, monkeypatch):
    main(["init"])  # the default world already exists
    monkeypatch.setattr(cli, "_stdin_is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", _answers("2"))

    assert main(["init", "--world", "adventure"]) == 0

    paths = EnvPaths(root=project / ".miney")
    assert manage.read_world_gameid(paths.world_dir("adventure")) == "mineclone2"


def test_init_keeps_an_existing_named_world_s_game_without_prompting(project, monkeypatch):
    main(["init", "--world", "adventure", "--game", "mineclone2"])
    monkeypatch.setattr(cli, "_stdin_is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", _refuse_input)

    # No --game: must reuse the world's own game, not prompt and not default to minetest.
    assert main(["init", "--world", "adventure"]) == 0


def test_init_does_not_prompt_without_a_terminal(project, monkeypatch):
    monkeypatch.setattr(cli, "_stdin_is_interactive", lambda: False)
    monkeypatch.setattr("builtins.input", _refuse_input)

    assert main(["init"]) == 0

    paths = EnvPaths(root=project / ".miney")
    assert (paths.world_dir(DEFAULT_GAME) / "world.mt").is_file()


def test_explicit_game_skips_the_prompt(project, monkeypatch):
    monkeypatch.setattr(cli, "_stdin_is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", _refuse_input)

    assert main(["init", "--game", "mineclone2"]) == 0

    paths = EnvPaths(root=project / ".miney")
    assert (paths.world_dir("VoxeLibre") / "world.mt").is_file()


def test_start_without_args_resumes_the_only_world(project):
    main(["init", "--game", "mineclone2"])  # creates the world "VoxeLibre"

    assert main(["start"]) == 0

    paths = EnvPaths(root=project / ".miney")
    assert load_state(paths.state_file("VoxeLibre")) is not None
    assert not paths.state_file("minetest_game").exists()


def test_picking_a_game_at_init_carries_into_start(project, monkeypatch):
    monkeypatch.setattr(cli, "_stdin_is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", _answers("2"))
    main(["init"])  # pick VoxeLibre -> world "VoxeLibre"

    monkeypatch.setattr("builtins.input", _refuse_input)  # start must not re-ask
    assert main(["start"]) == 0

    paths = EnvPaths(root=project / ".miney")
    assert load_state(paths.state_file("VoxeLibre")) is not None
    assert not paths.state_file("minetest_game").exists()


def test_start_prompts_for_the_game_on_first_run(project, monkeypatch):
    monkeypatch.setattr(cli, "_stdin_is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", _answers("2"))

    assert main(["start"]) == 0

    state = load_state(EnvPaths(root=project / ".miney").state_file("VoxeLibre"))
    assert state is not None
    assert state.gameid == "mineclone2"


@pytest.mark.parametrize(
    "answers,expected",
    [
        (["2"], "mineclone2"),
        (["1"], "minetest_game"),
        ([""], "minetest_game"),
        (["mineclone2"], "mineclone2"),
        (["x", "9", "1"], "minetest_game"),  # invalid answers re-ask until a valid one
    ],
)
def test_prompt_for_game_reads_the_choice(monkeypatch, capsys, answers, expected):
    monkeypatch.setattr("builtins.input", _answers(*answers))
    assert cli._prompt_for_game() == expected


def test_prompt_shows_voxelibre_with_its_id(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", _answers("1"))
    cli._prompt_for_game()
    assert "VoxeLibre (mineclone2)" in capsys.readouterr().out


def _eof_input(prompt=""):
    raise EOFError()


def test_prompt_for_game_falls_back_to_the_default_on_eof(monkeypatch):
    monkeypatch.setattr("builtins.input", _eof_input)
    assert cli._prompt_for_game() == "minetest_game"


def test_start_records_pids_and_port(project):
    assert main(["start"]) == 0

    state = load_state(EnvPaths(root=project / ".miney").state_file(DEFAULT_GAME))
    assert state is not None
    assert state.port == 30000
    assert state.server_pid == 4242
    assert state.client_pid == 4242


def test_start_without_client(project):
    assert main(["start", "--no-client"]) == 0

    state = load_state(EnvPaths(root=project / ".miney").state_file(DEFAULT_GAME))
    assert state is not None
    assert state.server_pid == 4242
    assert state.client_pid is None


def test_start_says_the_server_keeps_running_and_how_to_stop_it(project, capsys):
    main(["start"])

    out = capsys.readouterr().out
    assert "background" in out
    assert "uv run miney stop" in out


def test_start_stop_hint_is_plain_for_a_lone_world(project, capsys):
    main(["start", "--world", "castle", "--game", "mineclone2"])

    out = capsys.readouterr().out
    assert "uv run miney stop" in out
    # A bare stop resolves the only world, so the hint does not clutter it with --world.
    assert "--world" not in out


def test_start_names_the_world_in_the_stop_hint_when_several_exist(project, capsys):
    main(["init", "--world", "keep", "--game", "minetest_game"])
    main(["start", "--world", "castle", "--game", "mineclone2"])

    out = capsys.readouterr().out
    assert "uv run miney stop --world castle" in out


def test_stop_without_args_stops_the_lone_world(project, monkeypatch):
    main(["start", "--game", "mineclone2"])  # the only world, and it is mineclone2
    stopped = []
    monkeypatch.setattr(
        "miney.env.manage.stop_pid", lambda pid: stopped.append(pid) or True
    )

    assert main(["stop"]) == 0  # not "world minetest_game does not exist"

    assert stopped == [4242, 4242]  # server and client of the mineclone2 world


def test_logs_reads_the_lone_world(project, capsys):
    main(["start", "--game", "mineclone2"])
    paths = EnvPaths(root=project / ".miney")
    log = paths.log_file("VoxeLibre")
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("a line in the mineclone2 log\n", encoding="utf-8")
    capsys.readouterr()

    assert main(["logs"]) == 0

    assert "mineclone2 log" in capsys.readouterr().out


def test_start_does_not_respawn_a_running_server(project, monkeypatch):
    main(["start"])
    monkeypatch.setattr("miney.env.manage.is_pid_alive", lambda pid: True)
    spawned = []
    monkeypatch.setattr(
        "miney.env.manage.spawn_detached",
        lambda command, cwd, env=None: spawned.append(command) or 1,
    )

    assert main(["start"]) == 0
    assert spawned == []


def test_start_names_a_second_world_separately(project):
    main(["start"])
    assert main(["start", "--world", "castle", "--game", "mineclone2"]) == 0

    paths = EnvPaths(root=project / ".miney")
    assert (paths.world_dir("castle") / "world.mt").is_file()
    first = load_state(paths.state_file(DEFAULT_GAME))
    second = load_state(paths.state_file("castle"))
    assert first is not None and second is not None
    assert first.port != second.port


def test_status_lists_worlds(project, capsys):
    main(["start"])
    capsys.readouterr()  # discard the "start" output

    assert main(["status"]) == 0

    out = capsys.readouterr().out
    assert DEFAULT_GAME in out
    # Both of these can only come from the fixture's stubs: the version and source of
    # the fake install, and a server that only the stubbed is_server_up calls up. If
    # cmd_status ever went around manage again -- running the real discover() and the
    # real is_pid_alive() as subprocesses -- this test would fail instead of passing
    # by accident.
    assert "5.16.1 (path)" in out
    assert "server=running" in out


def test_status_shows_the_voxelibre_label(project, capsys):
    main(["init", "--game", "mineclone2"])
    capsys.readouterr()

    assert main(["status"]) == 0

    assert "VoxeLibre (mineclone2)" in capsys.readouterr().out


def test_status_calls_a_booting_server_starting_rather_than_running(
    project, monkeypatch, capsys
):
    """
    pid alive but the port still free is a server that is loading the game and
    generating the map. Calling that "running" sends a beginner to connect to
    something that answers with a timeout.
    """
    main(["start"])
    monkeypatch.setattr("miney.env.manage.is_pid_alive", lambda pid: True)
    monkeypatch.setattr("miney.env.manage.is_server_up", lambda state: False)
    capsys.readouterr()

    assert main(["status"]) == 0

    assert "server=starting" in capsys.readouterr().out


def test_status_without_an_environment(project, capsys):
    assert main(["status"]) == 0
    assert "miney start" in capsys.readouterr().out


def test_status_reports_a_world_that_was_never_started(project, capsys):
    """
    The defect this guards against: 'miney init' followed by 'miney status' used to
    say "No worlds yet", telling a beginner to create a world that already existed.
    """
    assert main(["init"]) == 0
    capsys.readouterr()  # discard the "init" output

    assert main(["status"]) == 0

    out = capsys.readouterr().out
    assert DEFAULT_GAME in out
    assert "never started" in out
    assert "uv run miney start" in out
    assert "No worlds yet" not in out


def test_status_says_no_worlds_yet_only_when_there_genuinely_is_none(project, capsys):
    (project / ".miney").mkdir()

    assert main(["status"]) == 0

    assert "No worlds yet" in capsys.readouterr().out


def test_status_mentions_a_newer_luanti(capsys, monkeypatch, tmp_path):
    paths = EnvPaths(root=tmp_path / ".miney")
    paths.root.mkdir(parents=True)
    monkeypatch.setattr(cli.manage, "find_environment", lambda: paths)
    monkeypatch.setattr(
        cli.manage, "describe",
        lambda p: manage.EnvironmentStatus(
            root=paths.root,
            install=LuantiInstall(launch=["luanti"], version=(5, 9, 0), source="path"),
            worlds=[],
            upstream=manage.upstream.Release((5, 16, 1), "5.16.1", {}),
        ),
    )

    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "5.16.1" in out


def test_status_says_nothing_about_versions_when_up_to_date(capsys, monkeypatch, tmp_path):
    paths = EnvPaths(root=tmp_path / ".miney")
    paths.root.mkdir(parents=True)
    monkeypatch.setattr(cli.manage, "find_environment", lambda: paths)
    monkeypatch.setattr(
        cli.manage, "describe",
        lambda p: manage.EnvironmentStatus(
            root=paths.root,
            install=LuantiInstall(launch=["luanti"], version=(5, 16, 1), source="path"),
            worlds=[],
            upstream=manage.upstream.Release((5, 16, 1), "5.16.1", {}),
        ),
    )

    assert cli.main(["status"]) == 0
    assert "newer" not in capsys.readouterr().out


def test_stop_clears_recorded_pids(project, monkeypatch):
    main(["start"])
    monkeypatch.setattr("miney.env.manage.is_pid_alive", lambda pid: True)
    monkeypatch.setattr("miney.env.manage.stop_pid", lambda pid: True)

    assert main(["stop"]) == 0

    state = load_state(EnvPaths(root=project / ".miney").state_file(DEFAULT_GAME))
    assert state is not None
    assert state.server_pid is None
    assert state.client_pid is None


def test_logs_prints_the_tail(project, capsys):
    main(["start"])
    paths = EnvPaths(root=project / ".miney")
    paths.log_file(DEFAULT_GAME).parent.mkdir(parents=True, exist_ok=True)
    paths.log_file(DEFAULT_GAME).write_text("ACTION: hello\n")

    assert main(["logs"]) == 0
    assert "ACTION: hello" in capsys.readouterr().out


def test_logs_explains_a_world_that_was_never_started(project, capsys):
    main(["init"])
    code = main(["logs"])
    assert code != 0
    assert "miney start" in capsys.readouterr().err


def test_remove_deletes_the_environment(project, monkeypatch):
    main(["init"])
    assert main(["remove", "--yes"]) == 0
    assert not (project / ".miney").exists()


def test_start_reports_a_missing_luanti_with_advice(project, monkeypatch, capsys):
    monkeypatch.setattr("miney.env.manage.discover", lambda paths: None)

    code = main(["start"])

    assert code != 0
    error = capsys.readouterr().err
    assert "luanti" in error.lower()


def _suggested_argv(error: str, lead: str = "miney start") -> list[str]:
    """Pull the suggested command out of an error message and split it into argv."""
    start = error.index(lead)
    line_end = error.find("\n", start)
    command = error[start:] if line_end == -1 else error[start:line_end]
    return command.strip().split()[1:]  # drop the leading "miney"


def test_stop_suggests_a_start_command_that_actually_works(project, capsys):
    # A world created with --game mineclone2 is named "VoxeLibre". Stopping it before it
    # was ever started must suggest a start command that recreates exactly that world.
    main(["init", "--game", "mineclone2"])

    code = main(["stop", "--game", "mineclone2"])

    assert code != 0
    error = capsys.readouterr().err
    assert "miney start" in error

    argv = _suggested_argv(error)
    assert main(argv) == 0

    state = load_state(EnvPaths(root=project / ".miney").state_file("VoxeLibre"))
    assert state is not None
    assert state.gameid == "mineclone2"


def test_stop_reports_a_world_that_was_never_created(project, capsys):
    main(["init"])  # environment exists, but "castle" specifically does not

    code = main(["stop", "--world", "castle", "--game", "mineclone2"])

    assert code != 0
    error = capsys.readouterr().err
    assert "does not exist" in error
    assert "castle" in error
    assert "miney init" in error


def test_logs_suggests_a_start_command_that_actually_works(project, capsys):
    # Reproduces "miney logs --world castle" suggesting a bare "miney start", which
    # would start the default world instead of "castle".
    main(["init", "--world", "castle", "--game", "mineclone2"])

    code = main(["logs", "--world", "castle"])

    assert code != 0
    error = capsys.readouterr().err
    assert "miney start" in error

    argv = _suggested_argv(error)
    assert main(argv) == 0

    state = load_state(EnvPaths(root=project / ".miney").state_file("castle"))
    assert state is not None
    assert state.gameid == "mineclone2"


def test_start_survives_a_missing_mod_source_when_already_installed(
    project, monkeypatch, capsys
):
    assert main(["start"]) == 0  # installs the real mod bundled with this checkout

    monkeypatch.setattr("miney.env.manage.mod_source", lambda: None)

    code = main(["start"])

    assert code == 0
    warning = capsys.readouterr().err
    assert "could not" in warning.lower()
    assert "install" in warning.lower() or "installed" in warning.lower()


def test_init_fails_when_mod_source_is_missing_and_nothing_installed(
    project, monkeypatch, capsys
):
    monkeypatch.setattr("miney.env.manage.mod_source", lambda: None)

    code = main(["init"])

    assert code != 0
    assert "mod" in capsys.readouterr().err.lower()


def test_init_names_a_real_place_to_get_the_mod_when_pip_installed(
    project, monkeypatch, capsys
):
    """
    A `pip install miney` has no `mod/` directory on disk at all -- setup.py's
    find_packages() cannot pick it up, there is no MANIFEST.in, no package_data. The
    error must not tell that user to "copy the 'mod/miney' directory", naming a
    directory that does not exist for them; it must point at a real URL instead.
    """
    monkeypatch.setattr("miney.env.manage.mod_source", lambda: None)

    code = main(["init"])

    assert code != 0
    error = capsys.readouterr().err
    assert "https://" in error
    assert "content.luanti.org" in error or "github.com/miney-py/miney" in error


def test_remove_stops_the_running_server_and_client_first(project, monkeypatch, capsys):
    main(["start"])
    stopped = []
    monkeypatch.setattr(
        "miney.env.manage.stop_pid", lambda pid: stopped.append(pid) or True
    )

    assert main(["remove", "--yes"]) == 0

    assert stopped == [4242, 4242]
    output = capsys.readouterr().out
    assert "Stopped" in output or "stopped" in output


def test_remove_of_whole_environment_stops_every_world(project, monkeypatch, capsys):
    main(["start"])
    main(["start", "--world", "castle", "--game", "mineclone2"])
    stopped = []
    monkeypatch.setattr(
        "miney.env.manage.stop_pid", lambda pid: stopped.append(pid) or True
    )

    assert main(["remove", "--yes"]) == 0

    assert len(stopped) == 4
    output = capsys.readouterr().out
    assert DEFAULT_GAME in output
    assert "castle" in output


def test_remove_of_one_world_stops_only_that_worlds_processes(
    project, monkeypatch, capsys
):
    main(["start"])
    main(["start", "--world", "castle", "--game", "mineclone2"])
    stopped = []
    monkeypatch.setattr(
        "miney.env.manage.stop_pid", lambda pid: stopped.append(pid) or True
    )

    assert main(["remove", "--world", "castle", "--yes"]) == 0

    assert len(stopped) == 2
    output = capsys.readouterr().out
    assert "castle" in output


def test_remove_without_an_environment_names_a_command(project, capsys):
    code = main(["remove", "--yes"])

    assert code == 0
    assert "miney init" in capsys.readouterr().out


def test_remove_of_a_world_that_was_never_created_says_so(project, capsys):
    """
    rmtree(..., ignore_errors=True) silently no-ops on a directory that never
    existed, so the old unconditional "Removed <path>" message was simply false.
    """
    main(["init"])  # environment exists; "castle" specifically was never created

    code = main(["remove", "--world", "castle", "--yes"])

    assert code == 0
    output = capsys.readouterr().out
    assert "castle" in output
    assert "did not exist" in output.lower() or "nothing" in output.lower()


def test_stop_says_something_when_already_stopped(project, monkeypatch, capsys):
    """
    A beginner cannot tell a silent, successful no-op from a hang. stop_pid checks
    liveness with the real, unmocked is_pid_alive from its own module (the fixture
    only stubs miney.env.manage.is_pid_alive), so recorded-but-not-actually-alive pids are
    exactly what "already stopped" looks like here.
    """
    main(["start"])
    monkeypatch.setattr("miney.env.process.is_pid_alive", lambda pid: False)
    capsys.readouterr()  # discard the "start" output

    code = main(["stop"])

    assert code == 0
    output = capsys.readouterr().out
    assert "minetest_game" in output
    assert output.strip() != ""


def test_stop_without_an_environment_is_not_an_error(project, capsys):
    code = main(["stop"])

    assert code == 0
    assert "miney start" in capsys.readouterr().out


def test_logs_without_an_environment_is_not_an_error(project, capsys):
    code = main(["logs"])

    assert code == 0
    assert "miney start" in capsys.readouterr().out


def _fake_popen(monkeypatch, log: list, wait=lambda: 0, pid: int = 9999):
    """
    Replace subprocess.Popen in the command with a process that never really runs.

    :param log: Every command Popen was asked to run is appended here.
    :param wait: What ``wait()`` does; raise from it to simulate Ctrl+C.
    :param pid: The pid the fake process reports.
    """

    class FakePopen:
        def __init__(self, command, **kwargs):
            self.args = command
            self.pid = pid
            log.append(command)

        def wait(self, timeout=None):
            return wait()

    monkeypatch.setattr("miney.cli.subprocess.Popen", FakePopen)
    return FakePopen


def test_foreground_does_not_spawn_a_detached_server_first(project, monkeypatch, capsys):
    """
    -f/--foreground must not spawn a detached server, point a client at it, then kill
    it in favour of a second, synchronous one -- the client would be pointed at the
    process that just died, and the two servers would race for the port and the
    world's sqlite lock.
    """
    spawned = []
    monkeypatch.setattr(
        "miney.env.manage.spawn_detached",
        lambda command, cwd, env=None: spawned.append(command) or 4242,
    )
    ran = []
    _fake_popen(monkeypatch, ran)

    assert main(["start", "--foreground"]) == 0

    # Only the client was ever spawned detached; the server ran synchronously instead.
    assert len(spawned) == 1
    assert "--go" in spawned[0]
    assert len(ran) == 1
    assert "--server" in ran[0]


def test_foreground_records_the_servers_pid_while_it_runs(project, monkeypatch):
    """
    subprocess.run threw the pid away, so status called the world stopped, autostart
    started a second server on the same port, and remove --yes rmtree'd a live world.
    """
    state_file = EnvPaths(root=project / ".miney").state_file(DEFAULT_GAME)
    seen: list[int | None] = []

    def wait():
        state = load_state(state_file)
        seen.append(state.server_pid if state is not None else None)
        return 0

    _fake_popen(monkeypatch, [], wait=wait)

    assert main(["start", "--foreground"]) == 0

    assert seen == [9999]  # visible to everything else while it runs
    state = load_state(state_file)
    assert state is not None
    assert state.server_pid is None  # and forgotten once it is over


def test_foreground_forgets_the_pid_when_you_press_ctrl_c(project, monkeypatch):
    def interrupted():
        raise KeyboardInterrupt

    _fake_popen(monkeypatch, [], wait=interrupted)

    assert main(["start", "--foreground"]) == 0

    state = load_state(EnvPaths(root=project / ".miney").state_file(DEFAULT_GAME))
    assert state is not None
    assert state.server_pid is None


def test_ctrl_c_during_the_client_wait_lets_the_server_finish_before_clearing_the_pid(
    project, monkeypatch
):
    """
    Ctrl+C can land inside open_client_when_up's up-to-120-second readiness wait, well
    before process.wait() is ever called. Clearing the recorded server pid without
    giving the child a chance to actually exit is exactly the failure the foreground
    pid recording was added to prevent: status calls a still-shutting-down server
    "stopped", and a follow-up start races it for the world's files.
    """
    order: list[str] = []

    def interrupted_client_wait(paths, world, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("miney.cli.manage.open_client_when_up", interrupted_client_wait)

    class FakePopen:
        def __init__(self, command, **kwargs):
            self.pid = 9999

        def wait(self, timeout=None):
            order.append("wait")
            return 0

    monkeypatch.setattr("miney.cli.subprocess.Popen", FakePopen)

    real_clear = manage.clear_foreground_server

    def spy_clear(paths, world, pid):
        order.append("clear")
        return real_clear(paths, world, pid)

    monkeypatch.setattr("miney.cli.manage.clear_foreground_server", spy_clear)

    assert main(["start", "--foreground"]) == 0

    assert order == ["wait", "clear"]


def test_foreground_exits_nonzero_when_the_server_dies_on_its_own(project, monkeypatch):
    """
    The detached path already returns 1 when the server cannot be reached; a
    foreground server that dies by itself (a bad port bind, a corrupt world) must not
    silently report success just because process.wait() returned.
    """

    class FakePopen:
        def __init__(self, command, **kwargs):
            self.pid = 9999

        def wait(self, timeout=None):
            return 1

    monkeypatch.setattr("miney.cli.subprocess.Popen", FakePopen)

    assert main(["start", "--foreground"]) == 1


def test_foreground_ctrl_c_exits_zero_even_though_the_child_also_exits_nonzero(
    project, monkeypatch
):
    """
    A plain Ctrl+C makes the child exit non-zero too (it was just killed by the
    signal); a naive "non-zero means failure" fix would wrongly report that as an
    error, unlike a server that dies unprompted.
    """
    calls: list[int] = []

    class FakePopen:
        def __init__(self, command, **kwargs):
            self.pid = 9999

        def wait(self, timeout=None):
            calls.append(1)
            if len(calls) == 1:
                raise KeyboardInterrupt
            return 1

    monkeypatch.setattr("miney.cli.subprocess.Popen", FakePopen)

    assert main(["start", "--foreground"]) == 0
    assert len(calls) == 2


def test_foreground_opens_the_client_after_the_server_is_up(project, monkeypatch):
    """The client is spawned by the front end, once the server process exists and
    answers -- not before it has even been started."""
    order: list[str] = []
    monkeypatch.setattr(
        "miney.env.manage.spawn_detached",
        lambda command, cwd, env=None: order.append("client") or 4242,
    )
    monkeypatch.setattr(
        "miney.env.manage.wait_until_up", lambda paths, state, **kwargs: order.append("wait")
    )

    class FakePopen:
        def __init__(self, command, **kwargs):
            order.append("server")
            self.pid = 9999

        def wait(self):
            order.append("exit")
            return 0

    monkeypatch.setattr("miney.cli.subprocess.Popen", FakePopen)

    assert main(["start", "--foreground"]) == 0

    assert order == ["server", "wait", "client", "exit"]


def test_foreground_start_mentions_a_newer_luanti_only_once(project, monkeypatch, capsys):
    """
    A foreground start with a client calls find_luanti() twice in one run - once
    inside start() itself, again inside open_client_when_up() once the server answers
    - and both share the same report callback. Regression test for the duplicate
    "A newer Luanti is available" notice that produced.
    """
    monkeypatch.setattr(
        "miney.env.manage.discover",
        lambda paths: LuantiInstall(launch=["/opt/luanti"], version=(5, 9, 0), source="path"),
    )
    monkeypatch.setattr(
        "miney.env.manage.upstream.latest_release",
        lambda p: manage.upstream.Release((5, 16, 1), "5.16.1", {}),
    )
    _fake_popen(monkeypatch, [])

    assert main(["start", "--foreground"]) == 0

    out = capsys.readouterr().out
    assert out.count("A newer Luanti is available: 5.16.1") == 1


def test_foreground_popen_receives_the_game_environment(project, monkeypatch):
    """
    The foreground branch runs the server command itself, so it has to pass on the
    same environment the detached path gets (see process.game_env) or a game Miney
    installed into .miney is invisible to a server run this way. Asserting on the
    kwargs Popen was actually called with is what test_foreground_records_the_servers_pid
    and friends never do -- they only check the command and the pid.
    """
    sentinel = {"LUANTI_GAME_PATH": "/fake/games"}
    monkeypatch.setattr("miney.env.manage.game_env", lambda paths: sentinel)
    captured: dict = {}

    class FakePopen:
        def __init__(self, command, **kwargs):
            captured.update(kwargs)
            self.pid = 9999

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr("miney.cli.subprocess.Popen", FakePopen)

    assert main(["start", "--foreground"]) == 0

    assert captured.get("env") is sentinel


def test_foreground_without_a_client_opens_nothing(project, monkeypatch):
    spawned = []
    monkeypatch.setattr(
        "miney.env.manage.spawn_detached",
        lambda command, cwd, env=None: spawned.append(command) or 4242,
    )
    _fake_popen(monkeypatch, [])

    assert main(["start", "--foreground", "--no-client"]) == 0

    assert spawned == []


def test_foreground_reports_a_server_that_will_not_start(project, monkeypatch, capsys):
    """Popen's OSError must become a clean message, not 'unexpected error'."""

    def refuse(command, **kwargs):
        raise FileNotFoundError("The system cannot find the file specified")

    monkeypatch.setattr("miney.cli.subprocess.Popen", refuse)

    code = main(["start", "--foreground"])

    assert code != 0
    error = capsys.readouterr().err
    assert "unexpected error" not in error
    assert "uv run miney start" in error


def test_foreground_refuses_when_the_server_already_runs(project, monkeypatch, capsys):
    """A foreground copy would fight the already-running one for the port and the
    world's save file, so refuse instead of racing it."""
    main(["start"])
    monkeypatch.setattr("miney.env.manage.is_pid_alive", lambda pid: True)
    ran = []
    _fake_popen(monkeypatch, ran)

    code = main(["start", "--foreground"])

    assert code != 0
    assert ran == []
    assert "miney stop" in capsys.readouterr().err


def test_start_with_explicit_port_is_idempotent_against_its_own_server(
    project, monkeypatch
):
    """
    Running 'miney start --port N' a second time against a world whose own server
    already holds N must succeed, not fail with "already in use by something else".
    """
    assert main(["start", "--port", "30000"]) == 0

    # The port really is busy now -- by our own recorded server.
    monkeypatch.setattr("miney.env.manage.is_pid_alive", lambda pid: True)
    monkeypatch.setattr("miney.env.manage.is_port_free", lambda port, host="127.0.0.1": False)
    monkeypatch.setattr(
        "miney.env.process.is_port_free", lambda port, host="127.0.0.1": False
    )

    assert main(["start", "--port", "30000"]) == 0


def test_start_reports_no_free_port_cleanly(project, monkeypatch, capsys):
    """find_free_port's OSError must become a clean message, not a traceback."""

    def raise_no_free_port(start=30000, attempts=20):
        raise OSError(
            f"No free port between {start} and {start + attempts - 1}. "
            f"Choose one yourself with: uv run miney start --port <number>"
        )

    monkeypatch.setattr("miney.env.manage.find_free_port", raise_no_free_port)

    code = main(["start"])

    assert code != 0
    error = capsys.readouterr().err
    assert "port" in error.lower()


def test_ctrl_c_is_a_message_and_an_exit_code_not_a_traceback(project, monkeypatch, capsys):
    """
    KeyboardInterrupt is a BaseException, so the "except Exception" boundary let it
    through as a raw traceback -- most likely during the readiness wait, which is
    where a user actually presses Ctrl+C.
    """

    def interrupt(args):
        raise KeyboardInterrupt

    monkeypatch.setattr("miney.cli.cmd_status", interrupt)

    code = main(["status"])

    assert code == 130  # 128 + SIGINT, what a shell expects from an interrupt
    error = capsys.readouterr().err
    assert "Traceback" not in error
    assert "miney logs" in error


def test_an_unexpected_error_names_its_type(project, monkeypatch, capsys):
    """A TypeError with an empty message used to print 'unexpected error:' and
    nothing else, leaving a bug report with nothing in it."""

    def boom(args):
        raise TypeError()

    monkeypatch.setattr("miney.cli.cmd_status", boom)

    code = main(["status"])

    assert code != 0
    error = capsys.readouterr().err
    assert "TypeError" in error
    assert "MINEY_DEBUG" in error


def test_the_debug_variable_brings_the_traceback_back(project, monkeypatch, capsys):
    def boom(args):
        raise TypeError("something internal broke")

    monkeypatch.setattr("miney.cli.cmd_status", boom)
    monkeypatch.setenv("MINEY_DEBUG", "1")

    assert main(["status"]) != 0

    assert "Traceback" in capsys.readouterr().err


def test_an_unexpected_error_is_logged_with_its_traceback(project, monkeypatch, caplog):
    def boom(args):
        raise TypeError("something internal broke")

    monkeypatch.setattr("miney.cli.cmd_status", boom)

    main(["status"])

    assert "Traceback" in caplog.text


def test_init_reports_a_locked_mod_install_cleanly(project, monkeypatch, capsys):
    """install_mod's shutil.rmtree can raise PermissionError on Windows when a file
    inside a running world's worldmods/ is locked; that must become a clean message
    naming the world, not a raw traceback."""

    def raise_permission_error(world_dir, source):
        raise PermissionError("The process cannot access the file because it is in use")

    monkeypatch.setattr("miney.env.manage.install_mod", raise_permission_error)

    code = main(["init"])

    assert code != 0
    error = capsys.readouterr().err
    assert "minetest_game" in error
    assert "miney init" in error


# --- miney check --------------------------------------------------------------------


def _report(*steps) -> "check.CheckReport":
    from miney.env import check

    return check.CheckReport(list(steps))


def _step(name, state, detail="", hint="", remedy=None):
    from miney.env import check

    return check.CheckStep(name=name, state=state, detail=detail, hint=hint, remedy=remedy)


def _remedy(applied: list, what="start the server", command="uv run miney start"):
    from miney.env import check

    return check.Remedy(
        what=what, command=command, apply=lambda report: applied.append(what)
    )


def _green():
    from miney.env import check

    return _report(
        _step("Miney", check.OK, "0.6.0"),
        _step("Luanti", check.OK, "5.16.1 (bundled)"),
    )


def _broken(applied=None):
    from miney.env import check

    return _report(
        _step("Miney", check.OK, "0.6.0"),
        _step(
            "Server",
            check.FAILED,
            "not running",
            remedy=_remedy(applied) if applied is not None else None,
        ),
    )


def test_check_prints_every_step_and_succeeds(project, monkeypatch, capsys):
    main(["init"])
    capsys.readouterr()
    monkeypatch.setattr("miney.env.check.run_checks", lambda *a, **k: _green())

    code = main(["check"])

    out = capsys.readouterr().out
    assert code == 0
    assert "Miney" in out and "Luanti" in out and "5.16.1 (bundled)" in out


def test_check_fails_with_a_non_zero_exit_code(project, monkeypatch, capsys):
    main(["init"])
    capsys.readouterr()
    monkeypatch.setattr("miney.env.check.run_checks", lambda *a, **k: _broken())

    assert main(["check"]) == 1


def test_check_names_the_command_that_fixes_the_problem(project, monkeypatch, capsys):
    applied: list = []
    main(["init"])
    capsys.readouterr()
    monkeypatch.setattr("miney.env.check.run_checks", lambda *a, **k: _broken(applied))
    monkeypatch.setattr(cli, "_stdin_is_interactive", lambda: False)

    main(["check"])

    out = capsys.readouterr().out + capsys.readouterr().err
    assert "uv run miney start" in out
    assert applied == []


def test_check_offers_the_fix_and_applies_it_when_told_to(project, monkeypatch, capsys):
    applied: list = []
    main(["init"])
    capsys.readouterr()
    reports = [_broken(applied), _green()]
    monkeypatch.setattr("miney.env.check.run_checks", lambda *a, **k: reports.pop(0))
    monkeypatch.setattr(cli, "_stdin_is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    code = main(["check"])

    out = capsys.readouterr().out
    assert applied == ["start the server"]
    assert code == 0
    # The question says what will happen and shows the command it stands for, so the
    # learner could have run it themselves.
    assert "start the server" in out
    assert "uv run miney start" in out


def test_check_does_nothing_when_the_offer_is_declined(project, monkeypatch, capsys):
    applied: list = []
    main(["init"])
    capsys.readouterr()
    monkeypatch.setattr("miney.env.check.run_checks", lambda *a, **k: _broken(applied))
    monkeypatch.setattr(cli, "_stdin_is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")

    code = main(["check"])

    assert applied == []
    assert code == 1
    assert "uv run miney start" in capsys.readouterr().out


def test_check_never_asks_without_a_terminal(project, monkeypatch, capsys):
    # Piped, redirected or in CI: report and exit, never block on a question nobody
    # will answer.
    applied: list = []
    main(["init"])
    capsys.readouterr()
    monkeypatch.setattr("miney.env.check.run_checks", lambda *a, **k: _broken(applied))
    monkeypatch.setattr(cli, "_stdin_is_interactive", lambda: False)

    def no_input(prompt=""):
        raise AssertionError("check must not prompt without a terminal")

    monkeypatch.setattr("builtins.input", no_input)

    assert main(["check"]) == 1
    assert applied == []


def test_check_tries_a_fix_only_once_per_step(project, monkeypatch, capsys):
    # The fix ran and the step is still broken: asking again would loop forever.
    # init runs before the stubs go in - with a stubbed interactive stdin it would hit
    # the game prompt, which rejects "y" and asks again forever.
    applied: list = []
    main(["init"])
    capsys.readouterr()
    monkeypatch.setattr(
        "miney.env.check.run_checks", lambda *a, **k: _broken(applied)
    )
    monkeypatch.setattr(cli, "_stdin_is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    code = main(["check"])

    assert code == 1
    assert applied == ["start the server"]


def test_check_offers_the_last_resort_when_it_fails(project, monkeypatch, capsys):
    main(["init"])
    capsys.readouterr()
    monkeypatch.setattr("miney.env.check.run_checks", lambda *a, **k: _broken())
    monkeypatch.setattr(cli, "_stdin_is_interactive", lambda: False)

    main(["check"])

    out = capsys.readouterr().out
    assert "Luanti" in out
    assert "uv run miney remove --yes" in out
    # The harmless one first, and the one that destroys built worlds clearly marked.
    assert out.index("Luanti") < out.index("uv run miney remove --yes")
    assert "no undo" in out.lower() or "cannot be undone" in out.lower()


def test_check_stays_quiet_about_the_last_resort_when_all_is_well(
    project, monkeypatch, capsys
):
    main(["init"])
    capsys.readouterr()
    monkeypatch.setattr("miney.env.check.run_checks", lambda *a, **k: _green())

    main(["check"])

    assert "miney remove --yes" not in capsys.readouterr().out


def test_check_without_an_environment_says_so(project, capsys):
    code = main(["check"])

    assert code == 1
    assert "miney init" in capsys.readouterr().out
