"""Tests for miney.env.check."""
from pathlib import Path

import pytest

from miney.env import check
from miney.env.paths import EnvPaths
from miney.env.world import DEFAULT_GAME, write_world_mt
from miney.exceptions import MineyRunError

WORLD = "testworld"


class FakePlayer:
    def __init__(self, name: str, privileges: list[str]):
        self.name = name
        self.privileges = privileges


class FakeConnection:
    """
    Stands in for a connected :class:`~miney.luanti.Luanti`.

    Only the handful of members the checks actually read, so a test never needs a
    server, a socket or the client protocol.
    """

    def __init__(self, *, version="5.16.1", privileges=("miney",), nodes=400, tools=30):
        self.version = version
        self.playername = "miney"
        self.players = [FakePlayer("miney", list(privileges))]
        self.nodes = type("N", (), {"names": ["node"] * nodes})()
        self.tool = ["tool"] * tools
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True
        return False


def _env(tmp_path: Path, *, world=True, mod=True, luanti=True) -> EnvPaths:
    """An environment on disk, with pieces left out on request."""
    paths = EnvPaths(root=tmp_path / ".miney")
    paths.root.mkdir(parents=True)
    if luanti:
        (paths.luanti_dir / "bin").mkdir(parents=True)
        (paths.luanti_dir / "bin" / "luanti").write_text("binary")
    if world:
        write_world_mt(paths.world_dir(WORLD), DEFAULT_GAME)
    if mod:
        target = paths.world_dir(WORLD) / "worldmods" / "miney"
        target.mkdir(parents=True)
        source = check.manage.mod_source()
        for item in source.iterdir():
            if item.is_file():
                (target / item.name).write_bytes(item.read_bytes())
    return paths


def _install(version=(5, 16, 1), source="bundled"):
    from miney.env.discover import LuantiInstall

    return LuantiInstall(launch=["luanti"], version=version, source=source)


def _run(paths, **kwargs):
    """run_checks with every outward-facing step stubbed unless overridden."""
    kwargs.setdefault("discover", lambda p: _install())
    kwargs.setdefault("server_up", lambda p, w: (True, 30000))
    kwargs.setdefault("connect", lambda w: FakeConnection())
    return check.run_checks(paths, WORLD, DEFAULT_GAME, **kwargs)


def _step(report, name):
    for step in report.steps:
        if step.name == name:
            return step
    raise AssertionError(f"no step named {name!r} in {[s.name for s in report.steps]}")


# --- the happy path -----------------------------------------------------------------


def test_a_complete_setup_passes_every_step(tmp_path):
    report = _run(_env(tmp_path))
    assert report.ok
    assert report.failure is None
    assert [step.state for step in report.steps] == [check.OK] * len(report.steps)


def test_the_first_step_names_the_miney_version(tmp_path):
    import miney

    assert miney.__version__ in _step(_run(_env(tmp_path)), "Miney").detail


def test_luanti_step_names_the_version_and_where_it_came_from(tmp_path):
    step = _step(_run(_env(tmp_path)), "Luanti")
    assert "5.16.1" in step.detail
    assert "bundled" in step.detail


def test_the_connection_is_closed_again(tmp_path):
    # A check that leaves a client logged in would keep the player in the world and
    # make the next connection fail with "already connected with this name".
    opened = []

    def connect(world):
        connection = FakeConnection()
        opened.append(connection)
        return connection

    _run(_env(tmp_path), connect=connect)
    assert opened and all(connection.closed for connection in opened)


# --- a broken setup, layer by layer -------------------------------------------------


def test_a_missing_luanti_fails_and_stops_the_chain(tmp_path):
    report = _run(_env(tmp_path, luanti=False), discover=lambda p: None)

    assert not report.ok
    assert report.failure.name == "Luanti"
    # Nothing below it was even looked at: a check that cannot find Luanti has nothing
    # useful to say about the world, the mod or the server.
    assert [step.name for step in report.steps] == ["Miney", "Luanti"]


def test_a_missing_luanti_offers_to_download_one(tmp_path):
    step = _run(_env(tmp_path, luanti=False), discover=lambda p: None).failure
    assert step.remedy is not None
    assert step.remedy.command == "uv run miney init"


def test_a_missing_world_fails_and_offers_to_create_it(tmp_path):
    report = _run(_env(tmp_path, world=False, mod=False))

    assert report.failure.name == "World"
    assert f"--world {WORLD}" in report.failure.remedy.command
    assert [step.name for step in report.steps] == ["Miney", "Luanti", "World"]


def test_a_missing_mod_fails_and_offers_to_install_it(tmp_path):
    report = _run(_env(tmp_path, mod=False))

    assert report.failure.name == "Miney mod"
    assert report.failure.remedy is not None


def test_an_outdated_mod_is_a_warning_and_the_chain_goes_on(tmp_path):
    # The world still runs, it just runs an older mod than this Miney ships. Calling
    # that a failure would send a beginner fixing something that is not broken.
    paths = _env(tmp_path)
    (paths.world_dir(WORLD) / "worldmods" / "miney" / "init.lua").write_text("-- older\n")

    report = _run(paths)

    step = _step(report, "Miney mod")
    assert step.state == check.WARNING
    assert step.remedy is not None
    assert report.ok
    assert _step(report, "Server").state == check.OK


def test_a_stopped_server_fails_and_offers_to_start_it(tmp_path):
    report = _run(_env(tmp_path), server_up=lambda p, w: (False, None))

    assert report.failure.name == "Server"
    assert "miney start" in report.failure.remedy.command
    assert [step.name for step in report.steps] == [
        "Miney", "Luanti", "World", "Miney mod", "Server",
    ]


def test_a_stopped_server_is_never_connected_to(tmp_path):
    # Connecting would autostart nothing, but it would still wait out a timeout for a
    # server the check already knows is down.
    def explode(world):
        raise AssertionError("connect must not be called when the server is down")

    _run(_env(tmp_path), server_up=lambda p, w: (False, None), connect=explode)


def test_a_refused_connection_fails_without_an_offer(tmp_path):
    # Nothing Miney can run fixes a handshake the server rejects, so no offer is made -
    # the step explains what to look at instead.
    def refuse(world):
        raise MineyRunError("Access denied: no miney mod on that server.")

    report = _run(_env(tmp_path), connect=refuse)

    assert report.failure.name == "Connection"
    assert report.failure.remedy is None
    assert "Access denied" in report.failure.detail


# --- the two steps that only ever warn ----------------------------------------------


def test_a_missing_privilege_is_only_a_warning_on_a_local_server(tmp_path):
    # mod_data/miney/init.lua lets a client on a local address run code without the
    # privilege, so the normal Miney setup does not need it at all.
    report = _run(_env(tmp_path), connect=lambda w: FakeConnection(privileges=()))

    step = _step(report, "Privilege")
    assert step.state == check.WARNING
    assert report.ok


def test_a_missing_privilege_names_the_grant_command(tmp_path):
    report = _run(_env(tmp_path), connect=lambda w: FakeConnection(privileges=()))
    step = _step(report, "Privilege")
    assert "/grant miney miney" in step.hint
    # Granting it goes through the very code execution it gates, so Miney cannot do it.
    assert step.remedy is None


def test_an_almost_empty_world_warns_about_its_content(tmp_path):
    report = _run(_env(tmp_path), connect=lambda w: FakeConnection(nodes=3, tools=0))

    step = _step(report, "Content")
    assert step.state == check.WARNING
    assert report.ok


def test_content_counts_are_reported(tmp_path):
    step = _step(_run(_env(tmp_path), connect=lambda w: FakeConnection(nodes=412, tools=34)),
                 "Content")
    assert "412" in step.detail
    assert "34" in step.detail


# --- applying a remedy --------------------------------------------------------------


def test_a_remedy_reports_what_it_does(tmp_path, monkeypatch):
    # The fix runs through manage, so it speaks through the same reporter every other
    # command uses rather than printing on its own. find_luanti is stubbed because
    # ensure_world calls it for real and the fake binary on disk cannot be run.
    said = []
    paths = _env(tmp_path, world=False, mod=False)
    monkeypatch.setattr(check.manage, "find_luanti", lambda p, report=None, **k: _install())
    remedy = _run(paths).failure.remedy

    remedy.apply(lambda progress: said.append(progress.message))

    assert said
    assert (paths.world_dir(WORLD) / "world.mt").is_file()


def test_the_remedy_for_a_stopped_server_does_not_open_a_client(tmp_path, monkeypatch):
    # "miney check" verifies, it does not put a game window on screen.
    seen = {}

    def fake_start(paths, world, game, **kwargs):
        seen.update(kwargs)

    monkeypatch.setattr(check.manage, "start", fake_start)
    report = _run(_env(tmp_path), server_up=lambda p, w: (False, None))
    report.failure.remedy.apply(None)

    assert seen["with_client"] is False
