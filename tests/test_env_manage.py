from __future__ import annotations
from pathlib import Path

import pytest

from miney.env import manage
from miney.env.discover import LuantiInstall
from miney.env.paths import EnvPaths
from miney.env.state import WorldState, load_state, save_state
from miney.env.world import DEFAULT_GAME
from miney.exceptions import MineyRunError

INSTALL = LuantiInstall(launch=["/opt/luanti"], version=(5, 16, 1), source="path")


class FakeClock:
    """A clock that only moves when something sleeps, so no test really waits."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def env(tmp_path, monkeypatch):
    """An environment whose Luanti, processes and ports are all stubbed."""
    paths = EnvPaths(root=tmp_path / ".miney")
    paths.root.mkdir(parents=True)
    monkeypatch.setattr(manage, "discover", lambda paths: INSTALL)
    monkeypatch.setattr(manage, "spawn_detached", lambda command, cwd, env=None: 4242)
    monkeypatch.setattr(manage, "is_pid_alive", lambda pid: False)
    monkeypatch.setattr(manage, "is_port_free", lambda port, host="127.0.0.1": True)
    monkeypatch.setattr(
        "miney.env.process.is_port_free", lambda port, host="127.0.0.1": True
    )
    # The stubbed server counts as up, so no test ever polls for readiness. The wait
    # itself is exercised directly by the wait_until_up tests below.
    monkeypatch.setattr(manage, "is_server_up", lambda state: True)
    # A silently skipped upstream lookup, not a real one: find_luanti() and describe()
    # both call it now, and a test suite must never make a real network request.
    monkeypatch.setattr(manage.upstream, "latest_release", lambda p: None)
    return paths


def _mod(source: Path, init: str = "-- old\n") -> Path:
    """Write a minimal mod source tree."""
    source.mkdir(parents=True, exist_ok=True)
    (source / "mod.conf").write_text("name = miney\n")
    (source / "init.lua").write_text(init)
    return source


# --- one definition of "up" (B2) ---------------------------------------------------


def test_a_live_pid_that_answers_the_handshake_is_up(monkeypatch):
    monkeypatch.setattr(manage, "is_pid_alive", lambda pid: True)
    monkeypatch.setattr(manage, "probe_server", lambda host, port: True)

    assert manage.is_server_up(WorldState("w", DEFAULT_GAME, 30000, server_pid=7)) is True


def test_a_booting_server_is_not_up_yet(monkeypatch):
    """pid alive but not yet answering the handshake is the mid-boot window that used to
    be mistaken for "already running"."""
    monkeypatch.setattr(manage, "is_pid_alive", lambda pid: True)
    monkeypatch.setattr(manage, "probe_server", lambda host, port: False)

    assert manage.is_server_up(WorldState("w", DEFAULT_GAME, 30000, server_pid=7)) is False


def test_a_dead_pid_is_not_our_server_even_if_the_port_answers(monkeypatch):
    monkeypatch.setattr(manage, "is_pid_alive", lambda pid: False)
    monkeypatch.setattr(manage, "probe_server", lambda host, port: True)

    assert manage.is_server_up(WorldState("w", DEFAULT_GAME, 30000, server_pid=7)) is False


# --- the readiness wait (B3) --------------------------------------------------------


def test_wait_returns_without_sleeping_when_the_server_is_already_up(tmp_path, monkeypatch):
    paths = EnvPaths(root=tmp_path / ".miney")
    clock = FakeClock()
    monkeypatch.setattr(manage, "is_server_up", lambda state: True)

    manage.wait_until_up(
        paths,
        WorldState("w", DEFAULT_GAME, 30000, server_pid=7),
        sleep=clock.sleep,
        clock=clock.monotonic,
    )

    assert clock.slept == []


def test_wait_polls_until_the_server_binds_its_port(tmp_path, monkeypatch):
    paths = EnvPaths(root=tmp_path / ".miney")
    clock = FakeClock()
    answers = iter([False, False, True])
    monkeypatch.setattr(manage, "is_server_up", lambda state: next(answers))
    monkeypatch.setattr(manage, "is_pid_alive", lambda pid: True)

    manage.wait_until_up(
        paths,
        WorldState("w", DEFAULT_GAME, 30000, server_pid=7),
        timeout=60,
        interval=0.5,
        sleep=clock.sleep,
        clock=clock.monotonic,
    )

    assert clock.slept == [0.5, 0.5]


def test_wait_times_out_naming_the_world_and_its_log(tmp_path, monkeypatch):
    paths = EnvPaths(root=tmp_path / ".miney")
    clock = FakeClock()
    monkeypatch.setattr(manage, "is_server_up", lambda state: False)
    monkeypatch.setattr(manage, "is_pid_alive", lambda pid: True)

    with pytest.raises(MineyRunError) as error:
        manage.wait_until_up(
            paths,
            WorldState("w", DEFAULT_GAME, 30000, server_pid=7),
            timeout=10,
            interval=1,
            sleep=clock.sleep,
            clock=clock.monotonic,
        )

    message = str(error.value)
    assert "'w'" in message
    assert str(paths.log_file("w")) in message
    assert "uv run miney logs" in message
    assert clock.now >= 10  # it stopped at the timeout instead of polling forever


def test_wait_fails_fast_when_the_server_dies_while_starting(tmp_path, monkeypatch):
    paths = EnvPaths(root=tmp_path / ".miney")
    clock = FakeClock()
    monkeypatch.setattr(manage, "is_server_up", lambda state: False)
    monkeypatch.setattr(manage, "is_pid_alive", lambda pid: False)

    with pytest.raises(MineyRunError) as error:
        manage.wait_until_up(
            paths,
            WorldState("w", DEFAULT_GAME, 30000, server_pid=7),
            timeout=600,
            sleep=clock.sleep,
            clock=clock.monotonic,
        )

    assert clock.slept == []  # not a single poll: the process is gone for good
    message = str(error.value)
    assert "'w'" in message
    assert str(paths.log_file("w")) in message


def test_wait_announces_itself_once(tmp_path, monkeypatch):
    paths = EnvPaths(root=tmp_path / ".miney")
    clock = FakeClock()
    answers = iter([False, False, True])
    monkeypatch.setattr(manage, "is_server_up", lambda state: next(answers))
    monkeypatch.setattr(manage, "is_pid_alive", lambda pid: True)
    messages: list[manage.Progress] = []

    manage.wait_until_up(
        paths,
        WorldState("w", DEFAULT_GAME, 30000, server_pid=7),
        interval=0.5,
        sleep=clock.sleep,
        clock=clock.monotonic,
        report=messages.append,
    )

    assert len(messages) == 1
    assert "start" in messages[0].message.lower()


# --- starting -----------------------------------------------------------------------


def test_start_creates_the_world_and_records_what_it_started(env):
    result = manage.start(env, DEFAULT_GAME, DEFAULT_GAME)

    assert (env.world_dir(DEFAULT_GAME) / "world.mt").is_file()
    assert result.state.server_pid == 4242
    assert result.state.client_pid == 4242
    assert result.foreground_command is None
    saved = load_state(env.state_file(DEFAULT_GAME))
    assert saved is not None and saved.port == 30000


def test_start_waits_for_the_server_before_returning(env, monkeypatch):
    waited: list[str] = []
    monkeypatch.setattr(
        manage, "wait_until_up", lambda paths, state, **kwargs: waited.append(state.name)
    )

    manage.start(env, "w", DEFAULT_GAME)

    assert waited == ["w"]


def test_start_reports_a_readiness_timeout_with_the_log_path(env, monkeypatch):
    monkeypatch.setattr(manage, "is_server_up", lambda state: False)
    monkeypatch.setattr(manage, "is_pid_alive", lambda pid: pid == 4242)

    with pytest.raises(MineyRunError) as error:
        manage.start(env, "w", DEFAULT_GAME, ready_timeout=0)

    assert str(env.log_file("w")) in str(error.value)


def test_ensure_world_finds_luanti_before_the_game(env, monkeypatch):
    """
    acquire_luanti() replaces paths.luanti_dir wholesale - shutil.rmtree() then a
    rename() over it - so installing a game before a fresh Luanti download would have
    it deleted again the moment that download lands. find_luanti() must therefore run
    before ensure_game(); reverting the order must fail this test.
    """
    order: list[str] = []
    monkeypatch.setattr(
        manage,
        "find_luanti",
        lambda paths, report=None, **kwargs: order.append("find_luanti") or INSTALL,
    )
    monkeypatch.setattr(
        manage,
        "ensure_game",
        lambda paths, gameid, report=None, **kwargs: order.append("ensure_game"),
    )

    manage.ensure_world(env, "w", DEFAULT_GAME)

    # ensure_game runs again for the preloaded games; only the first two steps matter here.
    assert order[:2] == ["find_luanti", "ensure_game"]


def test_ensure_world_returns_the_install_to_launch(env):
    """start() launches whatever ensure_world found, so ensure_world hands it back."""
    assert manage.ensure_world(env, "w", DEFAULT_GAME) == INSTALL


def test_start_in_the_foreground_hands_the_command_back_instead_of_spawning(env, monkeypatch):
    spawned: list[list[str]] = []
    monkeypatch.setattr(
        manage,
        "spawn_detached",
        lambda command, cwd, env=None: spawned.append(command) or 4242,
    )

    result = manage.start(env, DEFAULT_GAME, DEFAULT_GAME, foreground=True)

    assert result.foreground_command is not None
    assert "--server" in result.foreground_command
    assert result.state.server_pid is None
    # Nothing is spawned at all: the client would be pointed at a server that the
    # front end has not started yet, so opening it is left for later.
    assert spawned == []
    assert result.pending_client is True


def test_start_in_the_foreground_records_the_world_before_returning(env):
    """The front end needs somewhere to write the server's pid the moment it has one."""
    manage.start(env, "w", DEFAULT_GAME, foreground=True)

    assert load_state(env.state_file("w")) is not None


def test_start_without_a_client_has_nothing_pending_in_the_foreground(env):
    result = manage.start(env, "w", DEFAULT_GAME, foreground=True, with_client=False)

    assert result.pending_client is False


def test_start_passes_the_game_environment_to_the_detached_server(env, monkeypatch):
    """
    Without this, a server started detached cannot find a game Miney installed into
    .miney rather than the Luanti install itself (see process.game_env's docstring for
    the hardware fact this is built on). A silently dropped env= here would leave
    every other start() test green, since they never inspect what spawn_detached was
    called with.
    """
    sentinel = {"LUANTI_GAME_PATH": "/fake/games"}
    monkeypatch.setattr(manage, "game_env", lambda paths: sentinel)
    seen: list = []
    monkeypatch.setattr(
        manage,
        "spawn_detached",
        lambda command, cwd, env=None: seen.append(env) or 4242,
    )

    # with_client=False: the client is spawned separately (with no env of its own),
    # which would otherwise overwrite what this test is actually checking.
    manage.start(env, "w", DEFAULT_GAME, with_client=False)

    assert seen == [sentinel]


def test_start_in_the_foreground_sets_foreground_env_from_game_env(env, monkeypatch):
    """
    The front end runs the foreground command itself, so StartResult has to hand it
    the same environment the detached path gets rather than leaving it to inherit
    this process's - which is exactly what happens if foreground_env is silently
    dropped or left at its None default.
    """
    sentinel = {"LUANTI_GAME_PATH": "/fake/games"}
    monkeypatch.setattr(manage, "game_env", lambda paths: sentinel)

    result = manage.start(env, "w", DEFAULT_GAME, foreground=True)

    assert result.foreground_env is sentinel


def test_start_opens_the_client_only_after_the_server_answers(env, monkeypatch):
    """
    A --go client whose server is not accepting connections yet times out its
    handshake and drops the learner at the main menu, which is the same race the
    readiness wait was built for on the Python side.
    """
    order: list[str] = []
    monkeypatch.setattr(
        manage,
        "spawn_detached",
        lambda command, cwd, env=None: order.append(
            "client" if "--go" in command else "server"
        ) or 4242,
    )
    monkeypatch.setattr(
        manage,
        "wait_until_up",
        lambda paths, state, **kwargs: order.append("wait"),
    )

    manage.start(env, "w", DEFAULT_GAME)

    assert order == ["server", "wait", "client"]


def test_start_forwards_its_polling_knobs_to_the_readiness_wait(env, monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(
        manage, "wait_until_up", lambda paths, state, **kwargs: seen.update(kwargs)
    )
    clock = FakeClock()

    manage.start(
        env,
        "w",
        DEFAULT_GAME,
        ready_timeout=7,
        ready_interval=0.25,
        sleep=clock.sleep,
        clock=clock.monotonic,
    )

    assert seen["timeout"] == 7
    assert seen["interval"] == 0.25
    # == rather than "is": a bound method is a fresh object on every attribute access.
    assert seen["sleep"] == clock.sleep
    assert seen["clock"] == clock.monotonic


def test_start_really_waits_for_the_server_it_started(tmp_path, monkeypatch):
    """
    Every other start test stubs is_server_up, so the seam between start and the
    readiness wait is never exercised. This one runs both for real, with only the
    clock and the sleep injected, so nothing actually waits.
    """
    paths = EnvPaths(root=tmp_path / ".miney")
    paths.root.mkdir(parents=True)
    monkeypatch.setattr(manage, "discover", lambda paths: INSTALL)
    monkeypatch.setattr(manage, "spawn_detached", lambda command, cwd, env=None: 4242)
    monkeypatch.setattr(manage, "is_pid_alive", lambda pid: pid == 4242)
    monkeypatch.setattr(
        "miney.env.process.is_port_free", lambda port, host="127.0.0.1": True
    )
    # No handshake reply means "not listening yet"; the third probe gets an answer.
    answers = iter([False, False, True])
    monkeypatch.setattr(manage, "probe_server", lambda host, port: next(answers))
    clock = FakeClock()

    result = manage.start(
        paths,
        "w",
        DEFAULT_GAME,
        with_client=False,
        ready_interval=0.5,
        sleep=clock.sleep,
        clock=clock.monotonic,
    )

    assert clock.slept == [0.5, 0.5]
    assert result.state.server_pid == 4242


def test_a_client_that_will_not_start_leaves_the_server_recorded(env, monkeypatch):
    """
    The design says a failed client is a warning: the script still runs, the learner
    just has no window. Failing here used to leave the server running with its pid
    nowhere on disk - invisible to status, unreachable by stop.
    """

    def refuse_the_client(command, cwd, env=None):
        if "--go" in command:
            raise FileNotFoundError("The system cannot find the file specified")
        return 4242

    monkeypatch.setattr(manage, "spawn_detached", refuse_the_client)
    messages: list[manage.Progress] = []

    result = manage.start(env, "w", DEFAULT_GAME, report=messages.append)

    assert result.state.server_pid == 4242
    saved = load_state(env.state_file("w"))
    assert saved is not None and saved.server_pid == 4242
    assert any(progress.warning for progress in messages)


def test_a_server_that_cannot_be_reached_still_leaves_its_pid_on_disk(env, monkeypatch):
    """A start that dies in the readiness wait must not orphan the server either."""
    monkeypatch.setattr(manage, "is_server_up", lambda state: False)
    monkeypatch.setattr(manage, "is_pid_alive", lambda pid: pid == 4242)

    with pytest.raises(MineyRunError):
        manage.start(env, "w", DEFAULT_GAME, ready_timeout=0)

    saved = load_state(env.state_file("w"))
    assert saved is not None and saved.server_pid == 4242


def test_start_without_a_client(env):
    result = manage.start(env, DEFAULT_GAME, DEFAULT_GAME, with_client=False)

    assert result.state.client_pid is None


def test_start_never_prints(env, capsys):
    manage.start(env, DEFAULT_GAME, DEFAULT_GAME)

    assert capsys.readouterr() == ("", "")


def test_start_reports_progress_as_whole_sentences(env):
    messages: list[manage.Progress] = []

    manage.start(env, DEFAULT_GAME, DEFAULT_GAME, report=messages.append)

    assert all(isinstance(progress, manage.Progress) for progress in messages)
    assert any("Started Luanti server" in progress.message for progress in messages)
    assert all(progress.message.endswith(".") for progress in messages if not progress.warning)


def test_start_does_not_clobber_a_concurrent_change_during_the_client_wait(
    env, monkeypatch
):
    """
    Regression test: start() loaded/mutated its state object, blocked in
    wait_until_up, then saved the whole record afterwards -- overwriting whatever
    another process wrote to state.json in the meantime. This fails against the old
    code: it saved the stale server_pid=4242 back over the concurrent 9999.
    """

    def concurrent_change_during_wait(paths, state, **kwargs):
        # Simulates another start taking the world over while this one is still
        # waiting for its own server to answer.
        concurrent = load_state(paths.state_file(state.name))
        concurrent.server_pid = 9999
        save_state(paths.state_file(state.name), concurrent)

    monkeypatch.setattr(manage, "wait_until_up", concurrent_change_during_wait)

    manage.start(env, "w", DEFAULT_GAME)

    saved = load_state(env.state_file("w"))
    assert saved is not None
    assert saved.server_pid == 9999  # the concurrent change survives
    assert saved.client_pid == 4242  # our own update still applies


def test_a_luanti_that_cannot_be_started_becomes_a_clean_error(env, monkeypatch):
    def refuse(command, cwd, env=None):
        raise FileNotFoundError("The system cannot find the file specified")

    monkeypatch.setattr(manage, "spawn_detached", refuse)

    with pytest.raises(MineyRunError) as error:
        manage.start(env, "w", DEFAULT_GAME)

    assert "uv run miney" in str(error.value)


def test_missing_luanti_names_where_to_get_one(env, monkeypatch):
    """
    find_luanti() branches on the real, platform-dependent acquire.can_acquire(): on
    an acquirable platform it tries to download and, with no reachable release, fails
    naming luanti.org; on Linux it would instead print package-manager instructions
    that never mention that domain (see test_find_luanti_reports_the_linux_instructions
    for that branch). can_acquire is stubbed here so this assertion holds regardless of
    which platform actually runs the suite - the whole point of this test is a message
    that helps *some* user find Luanti, not a specific one of the two branches.
    """
    monkeypatch.setattr(manage, "discover", lambda paths: None)
    monkeypatch.setattr(manage.acquire, "can_acquire", lambda *args, **kwargs: True)

    with pytest.raises(MineyRunError) as error:
        manage.find_luanti(env)

    assert "luanti.org" in str(error.value)


# --- acquiring a missing Luanti and game (Stage 2) -----------------------------------


def test_find_luanti_downloads_one_when_none_is_installed(tmp_path, monkeypatch):
    paths = EnvPaths(root=tmp_path / ".miney")
    downloaded = []

    monkeypatch.setattr(manage, "discover", lambda p: None)
    monkeypatch.setattr(manage.acquire, "can_acquire", lambda: True)
    monkeypatch.setattr(
        manage.upstream, "latest_release", lambda p: manage.upstream.Release((5, 16, 1), "5.16.1", {})
    )

    def fake_acquire(p, release):
        downloaded.append(release.tag)
        return p.luanti_dir

    monkeypatch.setattr(manage, "_acquire_and_rediscover", fake_acquire)
    monkeypatch.setattr(
        manage, "_discover_after_acquire",
        lambda p: LuantiInstall(launch=["luanti"], version=(5, 16, 1), source="bundled"),
    )

    install = manage.find_luanti(paths)
    assert install.source == "bundled"
    assert downloaded == ["5.16.1"]


def test_find_luanti_does_not_name_a_version_it_may_not_be_installing(
    tmp_path, monkeypatch
):
    # The notice used to name the upstream tag looked up a line earlier. On Linux the
    # download comes from the AppImage repository instead and can be a build behind, so
    # naming that tag would announce a version the user does not get. The version that
    # did land is reported by the "is ready" line straight afterwards, which is the one
    # place it can be stated truthfully.
    paths = EnvPaths(root=tmp_path / ".miney")
    said: list[str] = []

    monkeypatch.setattr(manage, "discover", lambda p: None)
    monkeypatch.setattr(manage.acquire, "can_acquire", lambda *a, **k: True)
    monkeypatch.setattr(
        manage.upstream,
        "latest_release",
        lambda p: manage.upstream.Release((5, 17, 0), "5.17.0", {}),
    )
    monkeypatch.setattr(manage, "_acquire_and_rediscover", lambda p, r: p.luanti_dir)
    monkeypatch.setattr(
        manage, "_discover_after_acquire",
        lambda p: LuantiInstall(launch=["luanti"], version=(5, 16, 1), source="bundled"),
    )

    manage.find_luanti(paths, report=lambda progress: said.append(progress.message))

    downloading = [message for message in said if "Downloading" in message]
    assert downloading and all("5.17.0" not in message for message in downloading)
    assert any("5.16.1 is ready" in message for message in said)


def test_find_luanti_instructs_when_it_has_no_download_for_this_machine(
    tmp_path, monkeypatch
):
    # A Linux architecture pkgforge does not build an AppImage for. Rare, but it must
    # still get the user running rather than leaving them with a failed download.
    paths = EnvPaths(root=tmp_path / ".miney")
    monkeypatch.setattr(manage, "discover", lambda p: None)
    monkeypatch.setattr(manage, "outdated_version", lambda p: None)
    monkeypatch.setattr(manage.acquire, "can_acquire", lambda: False)
    monkeypatch.setattr(manage.upstream, "latest_release", lambda p: None)

    with pytest.raises(MineyRunError, match="flatpak install flathub"):
        manage.find_luanti(paths)


def test_find_luanti_names_an_outdated_install_it_cannot_replace(tmp_path, monkeypatch):
    # A machine Miney has no download for, carrying a Luanti older than the mod needs:
    # discover() throws it away and returns None, but the user should be told the
    # version they have and the one required, not told to install Luanti from scratch.
    paths = EnvPaths(root=tmp_path / ".miney")
    monkeypatch.setattr(manage, "discover", lambda p: None)
    monkeypatch.setattr(manage, "outdated_version", lambda p: (5, 6, 0))
    monkeypatch.setattr(manage.acquire, "can_acquire", lambda: False)
    monkeypatch.setattr(manage.upstream, "latest_release", lambda p: None)

    with pytest.raises(MineyRunError) as excinfo:
        manage.find_luanti(paths)
    message = str(excinfo.value)
    assert "5.6.0" in message
    assert "5.7.0" in message
    assert "uv run miney start" in message


def test_find_luanti_mentions_a_newer_version_once(tmp_path, monkeypatch):
    paths = EnvPaths(root=tmp_path / ".miney")
    monkeypatch.setattr(
        manage, "discover",
        lambda p: LuantiInstall(launch=["luanti"], version=(5, 9, 0), source="path"),
    )
    monkeypatch.setattr(
        manage.upstream, "latest_release",
        lambda p: manage.upstream.Release((5, 16, 1), "5.16.1", {}),
    )
    seen = []

    manage.find_luanti(paths, report=seen.append)
    assert sum("5.16.1" in progress.message for progress in seen) == 1


def test_find_luanti_is_quiet_when_the_install_is_current(tmp_path, monkeypatch):
    paths = EnvPaths(root=tmp_path / ".miney")
    monkeypatch.setattr(
        manage, "discover",
        lambda p: LuantiInstall(launch=["luanti"], version=(5, 16, 1), source="path"),
    )
    monkeypatch.setattr(
        manage.upstream, "latest_release",
        lambda p: manage.upstream.Release((5, 16, 1), "5.16.1", {}),
    )
    seen = []

    manage.find_luanti(paths, report=seen.append)
    assert seen == []


def test_ensure_game_installs_a_missing_game(tmp_path, monkeypatch):
    paths = EnvPaths(root=tmp_path / ".miney")
    installed = []

    def fake_install(gameid, games_dir):
        installed.append((gameid, games_dir))
        (games_dir / gameid).mkdir(parents=True)
        return games_dir / gameid

    monkeypatch.setattr(manage.contentdb, "install_game", fake_install)
    manage.ensure_game(paths, "minetest_game")
    assert installed == [("minetest_game", paths.games_dir)]


def test_ensure_game_does_nothing_when_the_game_is_already_there(tmp_path, monkeypatch):
    paths = EnvPaths(root=tmp_path / ".miney")
    (paths.games_dir / "minetest_game").mkdir(parents=True)
    (paths.games_dir / "minetest_game" / "game.conf").write_text("title = x")

    def fail(gameid, games_dir):
        raise AssertionError("must not download a game that is already installed")

    monkeypatch.setattr(manage.contentdb, "install_game", fail)
    manage.ensure_game(paths, "minetest_game")


def test_ensure_game_accepts_a_game_the_luanti_install_already_ships(tmp_path, monkeypatch):
    # A system Luanti may carry minetest_game itself. Downloading a second copy into
    # .miney would work but is a pointless 3 MB on every new project.
    paths = EnvPaths(root=tmp_path / ".miney")
    bundled = tmp_path / "system-luanti" / "games" / "minetest_game"
    bundled.mkdir(parents=True)
    (bundled / "game.conf").write_text("title = x")

    def fail(gameid, games_dir):
        raise AssertionError("must not download a game the install already has")

    monkeypatch.setattr(manage.contentdb, "install_game", fail)
    manage.ensure_game(paths, "minetest_game", search=[bundled.parent])


# --- ports --------------------------------------------------------------------------


def test_an_explicit_busy_port_is_refused_with_one_to_try_instead(env, monkeypatch):
    monkeypatch.setattr(manage, "is_port_free", lambda port, host="127.0.0.1": False)

    with pytest.raises(MineyRunError) as error:
        manage.resolve_port(env, "w", 30000, None)

    assert "30001" in str(error.value)


def test_a_world_may_keep_the_port_its_own_server_already_holds(env, monkeypatch):
    monkeypatch.setattr(manage, "is_pid_alive", lambda pid: True)
    monkeypatch.setattr(manage, "is_port_free", lambda port, host="127.0.0.1": False)
    state = WorldState("w", DEFAULT_GAME, 30000, server_pid=7)

    assert manage.resolve_port(env, "w", 30000, state) == 30000


def test_no_free_port_becomes_a_clean_error(env, monkeypatch):
    def refuse(start=30000, attempts=20):
        raise OSError("No free port between 30000 and 30019.")

    monkeypatch.setattr(manage, "find_free_port", refuse)

    with pytest.raises(MineyRunError) as error:
        manage.resolve_port(env, "w", None, None)

    assert "port" in str(error.value).lower()


def test_a_second_world_does_not_reuse_the_first_worlds_port(env):
    manage.start(env, DEFAULT_GAME, DEFAULT_GAME)

    second = manage.start(env, "castle", DEFAULT_GAME)

    assert second.state.port != 30000


# --- the foreground server is a server like any other (C1) --------------------------


def test_a_recorded_foreground_server_is_visible_to_everything_else(env, monkeypatch, tmp_path):
    """
    'miney start --foreground' used to record no pid at all, so status called the
    world stopped, autostart started a second server on the same port, and the mod
    refresh happily replaced worldmods/miney under the running one.
    """
    source = _mod(tmp_path / "mod" / "miney")
    monkeypatch.setattr(manage, "mod_source", lambda: source)
    manage.start(env, "w", DEFAULT_GAME, foreground=True)

    state = manage.record_foreground_server(env, "w", 4711)

    assert state.server_pid == 4711
    saved = load_state(env.state_file("w"))
    assert saved is not None and saved.server_pid == 4711

    # status sees it running
    assert manage.describe(env).worlds[0].server == "running"

    # and the mod refresh leaves the world it is serving alone
    monkeypatch.setattr(manage, "is_pid_alive", lambda pid: pid == 4711)
    (source / "init.lua").write_text("-- upgraded\n")
    messages: list[manage.Progress] = []
    manage.ensure_world(env, "w", DEFAULT_GAME, report=messages.append)
    installed = env.world_dir("w") / "worldmods" / "miney" / "init.lua"
    assert installed.read_text() == "-- old\n"
    assert any(progress.warning for progress in messages)


def test_the_foreground_pid_is_forgotten_when_the_server_ends(env):
    manage.start(env, "w", DEFAULT_GAME, foreground=True)
    manage.record_foreground_server(env, "w", 4711)

    manage.clear_foreground_server(env, "w", 4711)

    saved = load_state(env.state_file("w"))
    assert saved is not None and saved.server_pid is None


def test_clearing_leaves_a_pid_that_belongs_to_somebody_else_alone(env):
    manage.start(env, "w", DEFAULT_GAME, foreground=True)
    manage.record_foreground_server(env, "w", 4711)

    manage.clear_foreground_server(env, "w", 1234)  # a different, older run

    saved = load_state(env.state_file("w"))
    assert saved is not None and saved.server_pid == 4711


def test_recording_a_foreground_server_without_a_world_names_a_command(env):
    with pytest.raises(MineyRunError) as error:
        manage.record_foreground_server(env, "w", 4711)

    assert "uv run miney start" in str(error.value)


def test_the_foreground_client_waits_for_the_server_then_opens(env, monkeypatch):
    manage.start(env, "w", DEFAULT_GAME, foreground=True)
    manage.record_foreground_server(env, "w", 4711)
    order: list[str] = []
    monkeypatch.setattr(
        manage, "wait_until_up", lambda paths, state, **kwargs: order.append("wait")
    )
    monkeypatch.setattr(
        manage,
        "spawn_detached",
        lambda command, cwd, env=None: order.append("client") or 4243,
    )

    manage.open_client_when_up(env, "w")

    assert order == ["wait", "client"]
    saved = load_state(env.state_file("w"))
    assert saved is not None and saved.client_pid == 4243
    assert saved.server_pid == 4711  # not clobbered


def test_a_concurrent_change_during_the_foreground_client_wait_is_not_undone(
    env, monkeypatch
):
    """
    Regression test: open_client_when_up used to load state once, block in
    wait_until_up for up to 120 seconds, then save that pre-wait snapshot -- silently
    overwriting anything another process wrote to state.json while it waited. This
    fails against the old code: it saved the stale server_pid=4711 back over the
    concurrent stop's None.
    """
    manage.start(env, "w", DEFAULT_GAME, foreground=True)
    manage.record_foreground_server(env, "w", 4711)

    def concurrent_stop_during_wait(paths, state, **kwargs):
        # Simulates "miney stop" running in another process while this call is still
        # waiting for the (foreground) server to answer.
        concurrent = load_state(paths.state_file("w"))
        concurrent.server_pid = None
        save_state(paths.state_file("w"), concurrent)

    monkeypatch.setattr(manage, "wait_until_up", concurrent_stop_during_wait)
    monkeypatch.setattr(manage, "spawn_detached", lambda command, cwd, env=None: 4243)

    manage.open_client_when_up(env, "w")

    saved = load_state(env.state_file("w"))
    assert saved is not None
    assert saved.server_pid is None  # the concurrent stop survives
    assert saved.client_pid == 4243  # our own update still applies


def test_a_foreground_client_that_never_opens_is_only_a_warning(env, monkeypatch):
    manage.start(env, "w", DEFAULT_GAME, foreground=True)
    manage.record_foreground_server(env, "w", 4711)
    monkeypatch.setattr(
        manage,
        "wait_until_up",
        lambda paths, state, **kwargs: (_ for _ in ()).throw(
            MineyRunError("did not finish starting")
        ),
    )
    messages: list[manage.Progress] = []

    manage.open_client_when_up(env, "w", report=messages.append)

    assert any(progress.warning for progress in messages)


# --- the read-only view behind "miney status" (C3) ----------------------------------


def test_describe_reports_a_running_a_starting_and_a_stopped_server(env, monkeypatch):
    save_state(env.state_file("up"), WorldState("up", DEFAULT_GAME, 30000, server_pid=1))
    save_state(env.state_file("boot"), WorldState("boot", DEFAULT_GAME, 30001, server_pid=2))
    save_state(env.state_file("down"), WorldState("down", DEFAULT_GAME, 30002))
    monkeypatch.setattr(manage, "is_pid_alive", lambda pid: pid in (1, 2))
    monkeypatch.setattr(manage, "is_server_up", lambda state: state.server_pid == 1)

    status = manage.describe(env)

    assert {world.state.name: world.server for world in status.worlds} == {
        "up": "running",
        "boot": "starting",
        "down": "stopped",
    }
    assert status.install is INSTALL


def test_describe_of_an_empty_environment_says_so(env):
    status = manage.describe(env)

    assert status.worlds == []
    assert status.root == env.root


def test_describe_reports_a_world_that_was_created_but_never_started(env):
    """
    'miney init' writes world.mt and never touches run/, so a world it just created
    has no state.json at all. describe() must still find it by reading worlds_dir
    directly -- this is the regression 'miney status' used to be blind to.
    """
    manage.write_world_mt(env.world_dir("castle"), "mineclone2")

    status = manage.describe(env)

    assert len(status.worlds) == 1
    world = status.worlds[0]
    assert world.name == "castle"
    assert world.gameid == "mineclone2"
    assert world.state is None
    assert world.server == manage.NEVER_STARTED
    assert world.client is None


def test_describe_merges_worlds_with_and_without_runtime_state(env):
    save_state(env.state_file("up"), WorldState("up", DEFAULT_GAME, 30000, server_pid=1))
    manage.write_world_mt(env.world_dir("castle"), "mineclone2")

    status = manage.describe(env)

    by_name = {world.name: world for world in status.worlds}
    assert set(by_name) == {"up", "castle"}
    assert by_name["up"].state is not None
    assert by_name["castle"].state is None
    assert by_name["castle"].server == manage.NEVER_STARTED


def test_describe_ignores_a_world_directory_without_a_readable_world_mt(env):
    """
    A half-finished 'miney remove' can leave an empty (or otherwise world.mt-less)
    directory under worlds/. That is not a world, and describe() must neither report
    it as one nor crash trying.
    """
    leftover = env.world_dir("ghost")
    leftover.mkdir(parents=True)
    (leftover / "worldmods").mkdir()

    status = manage.describe(env)

    assert status.worlds == []


def test_describe_reports_the_upstream_version(tmp_path, monkeypatch):
    paths = EnvPaths(root=tmp_path / ".miney")
    paths.root.mkdir(parents=True)
    monkeypatch.setattr(
        manage, "discover",
        lambda p: LuantiInstall(launch=["luanti"], version=(5, 9, 0), source="path"),
    )
    monkeypatch.setattr(
        manage.upstream, "latest_release",
        lambda p: manage.upstream.Release((5, 16, 1), "5.16.1", {}),
    )

    status = manage.describe(paths)
    assert status.upstream is not None
    assert status.upstream.version == (5, 16, 1)


def test_describe_survives_a_failed_upstream_lookup(tmp_path, monkeypatch):
    paths = EnvPaths(root=tmp_path / ".miney")
    paths.root.mkdir(parents=True)
    monkeypatch.setattr(manage, "discover", lambda p: None)
    monkeypatch.setattr(manage.upstream, "latest_release", lambda p: None)

    status = manage.describe(paths)
    assert status.upstream is None


# --- when the mod is refreshed (B4) -------------------------------------------------


def test_the_mod_is_not_recopied_when_it_is_already_current(env, monkeypatch, tmp_path):
    monkeypatch.setattr(manage, "mod_source", lambda: _mod(tmp_path / "mod" / "miney"))
    manage.ensure_world(env, "w", DEFAULT_GAME)
    copied: list[Path] = []
    monkeypatch.setattr(
        manage, "install_mod", lambda world_dir, source: copied.append(world_dir)
    )

    manage.ensure_world(env, "w", DEFAULT_GAME)

    assert copied == []


def test_an_upgraded_mod_reaches_an_existing_world(env, monkeypatch, tmp_path):
    source = _mod(tmp_path / "mod" / "miney")
    monkeypatch.setattr(manage, "mod_source", lambda: source)
    manage.ensure_world(env, "w", DEFAULT_GAME)

    (source / "init.lua").write_text("-- upgraded\n")
    manage.ensure_world(env, "w", DEFAULT_GAME)

    installed = env.world_dir("w") / "worldmods" / "miney" / "init.lua"
    assert installed.read_text() == "-- upgraded\n"


def test_replacing_the_mod_is_never_silent(env, monkeypatch, tmp_path):
    """install_mod replaces worldmods/miney whole, so it has to say so."""
    source = _mod(tmp_path / "mod" / "miney")
    monkeypatch.setattr(manage, "mod_source", lambda: source)
    manage.ensure_world(env, "w", DEFAULT_GAME)
    (source / "init.lua").write_text("-- upgraded\n")
    messages: list[manage.Progress] = []

    manage.ensure_world(env, "w", DEFAULT_GAME, report=messages.append)

    assert any("Refreshed the Miney mod" in progress.message for progress in messages)


def test_a_running_world_keeps_its_mod_directory(env, monkeypatch, tmp_path):
    source = _mod(tmp_path / "mod" / "miney")
    monkeypatch.setattr(manage, "mod_source", lambda: source)
    manage.ensure_world(env, "w", DEFAULT_GAME)
    save_state(env.state_file("w"), WorldState("w", DEFAULT_GAME, 30000, server_pid=7))
    monkeypatch.setattr(manage, "is_pid_alive", lambda pid: True)
    (source / "init.lua").write_text("-- upgraded\n")
    messages: list[manage.Progress] = []

    manage.ensure_world(env, "w", DEFAULT_GAME, report=messages.append)

    installed = env.world_dir("w") / "worldmods" / "miney" / "init.lua"
    assert installed.read_text() == "-- old\n"
    assert any(progress.warning for progress in messages)
    assert any("uv run miney stop" in progress.message for progress in messages)


def test_a_missing_mod_source_with_nothing_installed_points_at_a_download(env, monkeypatch):
    monkeypatch.setattr(manage, "mod_source", lambda: None)

    with pytest.raises(MineyRunError) as error:
        manage.ensure_world(env, "w", DEFAULT_GAME)

    assert "https://" in str(error.value)


def test_a_missing_mod_source_warns_when_one_is_already_installed(env, monkeypatch, tmp_path):
    monkeypatch.setattr(manage, "mod_source", lambda: _mod(tmp_path / "mod" / "miney"))
    manage.ensure_world(env, "w", DEFAULT_GAME)
    monkeypatch.setattr(manage, "mod_source", lambda: None)
    messages: list[manage.Progress] = []

    manage.ensure_world(env, "w", DEFAULT_GAME, report=messages.append)

    assert any(progress.warning for progress in messages)


def test_mod_source_ships_beside_the_package():
    # The mod ships as its own top-level 'mod_data' package, so it is present in a wheel
    # as well as in a checkout - sitting next to the miney package, one directory up from
    # it, in both.
    source = manage.mod_source()
    assert source is not None
    assert (source / "mod.conf").is_file()
    package_root = Path(manage.__file__).resolve().parent.parent.parent
    assert source == package_root / "mod_data" / "miney"


def test_a_locked_mod_directory_becomes_a_clean_error(env, monkeypatch):
    def refuse(world_dir, source):
        raise PermissionError("The process cannot access the file because it is in use")

    monkeypatch.setattr(manage, "install_mod", refuse)

    with pytest.raises(MineyRunError) as error:
        manage.ensure_world(env, "w", DEFAULT_GAME)

    assert "uv run miney" in str(error.value)


def test_ensure_world_installs_the_world_s_game_via_ensure_game(env, monkeypatch):
    """
    Regression seam: ensure_world must call ensure_game so that a world whose game
    lives only in .miney (not bundled with the Luanti install) actually gets it. A
    silently dropped call here would leave the whole suite green (the autouse
    _no_contentdb_download fixture fakes the game onto disk another way) while
    breaking real installs, so this asserts on the call itself.
    """
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        manage,
        "ensure_game",
        lambda paths, gameid, report=None: calls.append((gameid, report)),
    )

    messages: list[manage.Progress] = []
    manage.ensure_world(env, "w", DEFAULT_GAME, report=messages.append)

    # The world's own game is ensured first; the preloaded games follow (see the
    # dedicated preload test), so this only pins the world's game as the first call.
    assert calls[0] == (DEFAULT_GAME, messages.append)


def test_ensure_world_preloads_both_games(env, monkeypatch):
    """Both known games land in the shared install, so --game costs no download later."""
    ensured: list[str] = []
    monkeypatch.setattr(
        manage, "ensure_game", lambda paths, gameid, report=None: ensured.append(gameid)
    )

    manage.ensure_world(env, "w", DEFAULT_GAME)

    assert set(ensured) == set(manage.PRELOAD_GAMES)
    assert "mineclone2" in ensured


def test_ensure_world_survives_a_failed_preload(env, monkeypatch):
    """A world only needs its own game; a preloaded extra that will not download warns."""
    def flaky(paths, gameid, report=None):
        if gameid != DEFAULT_GAME:
            raise MineyRunError("ContentDB is down")

    monkeypatch.setattr(manage, "ensure_game", flaky)
    messages: list[manage.Progress] = []

    # Must not raise: the world's game succeeded, the extra did not.
    manage.ensure_world(env, "w", DEFAULT_GAME, report=messages.append)

    warnings = [m.message for m in messages if m.warning]
    assert any("mineclone2" in text and "optional" in text for text in warnings)


def test_a_world_cannot_change_its_game(env):
    manage.ensure_world(env, "w", DEFAULT_GAME)

    with pytest.raises(MineyRunError) as error:
        manage.ensure_world(env, "w", "mineclone2")

    assert "mineclone2" in str(error.value)
    assert "uv run miney" in str(error.value)


# --- stopping and removing ----------------------------------------------------------


def test_stop_clears_the_recorded_pids(env, monkeypatch):
    manage.start(env, "w", DEFAULT_GAME)
    monkeypatch.setattr(manage, "stop_pid", lambda pid: True)
    messages: list[manage.Progress] = []

    state = manage.stop(env, "w", DEFAULT_GAME, report=messages.append)

    assert state.server_pid is None and state.client_pid is None
    assert any("Stopped the server" in progress.message for progress in messages)


def test_stop_of_a_world_that_was_never_started_names_a_command(env):
    with pytest.raises(MineyRunError) as error:
        manage.stop(env, "w", DEFAULT_GAME)

    assert "uv run miney" in str(error.value)


def test_remove_stops_the_world_before_deleting_it(env, monkeypatch):
    manage.start(env, "w", DEFAULT_GAME)
    stopped: list[int] = []
    monkeypatch.setattr(manage, "stop_pid", lambda pid: stopped.append(pid) or True)

    manage.remove(env, "w")

    assert stopped == [4242, 4242]
    assert not env.world_dir("w").exists()
    assert not env.state_file("w").exists()


def test_remove_says_when_there_was_nothing_there(env):
    messages: list[manage.Progress] = []

    manage.remove(env, "castle", report=messages.append)

    assert any("did not exist" in progress.message for progress in messages)


# --- the machinery stays out of the teaching surface --------------------------------


def test_no_environment_machinery_leaks_into_the_public_api():
    import miney

    assert "manage" not in miney.__all__
    assert "cli" not in miney.__all__
    for name in miney.__all__:
        module = getattr(getattr(miney, name), "__module__", "")
        assert not module.startswith("miney.env"), name
        assert module != "miney.cli", name
