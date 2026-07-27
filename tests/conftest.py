"""
Shared pytest fixtures for Miney tests.
"""
from __future__ import annotations

import json

import pytest
from miney.lua import Lua, REQUIRED_MOD_API


class FakeTransport:
    """
    A transport that keeps everything in a list instead of sending it anywhere.

    This is the whole reason the file channel was worth building for the test suite as
    well: the old transport was a UDP state machine and had to be emulated packet by
    packet, while this one is "here is a dict, there is a dict". It offers exactly what
    :class:`~miney.channel.FileChannel` does, which is the list below and nothing else.

    :param mod_api: What the server's mod claims to speak.
    :param connected: Whether the transport reports itself usable.
    """

    def __init__(self, mod_api: int | None = REQUIRED_MOD_API, connected: bool = True):
        self.mod_api = mod_api
        self.sent: list[dict] = []
        self.listeners: list = []
        self.closed = False
        self._connected = connected

    @property
    def connected(self) -> bool:
        return self._connected

    def add_listener(self, listener) -> None:
        self.listeners.append(listener)

    def send(self, fields: dict) -> bool:
        self.sent.append(fields)
        return True

    def timeout_hint(self) -> str:
        return "The server did not answer."

    def close(self) -> None:
        self.closed = True

    def deliver(self, record: dict) -> None:
        """
        Hand one record to everything listening, the way a real answer arrives.

        :param record: What the mod would have sent.
        """
        for listener in list(self.listeners):
            listener(record)

    def deliver_json(self, text: str) -> None:
        """
        The same, for a test that has the record as JSON.

        :param text: One record, encoded.
        """
        self.deliver(json.loads(text))


@pytest.fixture
def fake_transport() -> FakeTransport:
    """A transport that records what was sent and replays what it is given."""
    return FakeTransport()


@pytest.fixture
def lua_for_dumps() -> Lua:
    """
    Provides a Lua instance only for testing Lua.dumps (no server interaction).
    """
    return Lua(FakeTransport())


@pytest.fixture(autouse=True)
def no_environment_lookup(monkeypatch):
    """
    Stop ``Luanti()`` from finding a real ``.miney`` environment during tests.

    ``find_env`` walks upward from the current working directory, so if a ``.miney``
    directory happens to exist at or above wherever pytest is run from, a plain
    ``luanti.Luanti()`` call in an unrelated test takes the environment path and can
    end up calling the real ``discover()`` (which spawns ``luanti --version``) and the
    real ``spawn_detached()`` (which starts a real server and GUI client).

    ``miney.env.manage`` holds its own binding of the same function (``from .paths
    import find_env``), which patching only ``miney.luanti.find_env`` would leave
    unprotected -- both modules bound the function object at import time, so patching
    the definition in ``miney.env.paths`` would not reach either of them. Both are
    patched here so the whole suite is covered by default, whichever front end a test
    happens to go through.

    Tests that specifically exercise the environment-lookup behaviour (see
    ``tests/test_luanti_env.py``) override this fixture locally to opt back in.
    """
    monkeypatch.setattr("miney.luanti.find_env", lambda start=None: None)
    monkeypatch.setattr("miney.env.manage.find_env", lambda start=None: None)


@pytest.fixture(autouse=True)
def _no_upstream_lookup(monkeypatch):
    """
    Keep the whole suite off the network.

    Patched where it is *used*, not where it is defined: ``manage`` binds the module
    object at import time, so patching ``miney.env.upstream.latest_release`` is what
    takes effect for every caller. A test that wants a release stubs it itself.
    """
    monkeypatch.setattr(
        "miney.env.upstream.latest_release", lambda *args, **kwargs: None
    )
    # Same for the Miney release on PyPI, which "status" and "upgrade" ask about.
    monkeypatch.setattr("miney.env.pypi.latest_version", lambda *args, **kwargs: None)
    # And no test may really run ensurepip: "miney init" installs pip into environments
    # that have none, and the interpreter running the suite is a real one. Pretending
    # pip is already there is the quiet stub - it is what most environments look like,
    # and it keeps the notice out of the output every other test asserts on. Tests for
    # the install path patch these two themselves.
    monkeypatch.setattr("miney.env.upgrade.has_pip", lambda: True)
    monkeypatch.setattr(
        "miney.env.upgrade.install_pip", lambda: "stubbed out in the test suite"
    )


@pytest.fixture(autouse=True)
def _no_contentdb_download(monkeypatch):
    """
    Keep the whole suite off ContentDB too.

    ``ensure_world`` now calls ``ensure_game`` unconditionally, which reaches for
    ``contentdb.install_game`` the moment a world's game is not already on disk -- and
    almost every ``ensure_world``/``start`` test builds a brand-new environment with no
    game in it at all. Faking the install here, by creating the very ``game.conf``
    ``ensure_game`` checks for, keeps every one of those tests off the network without
    each of them having to know ``ensure_game`` exists. A test that exercises
    ``ensure_game`` or ``contentdb.install_game`` itself overrides this locally.
    """
    def fake_install(gameid, games_dir):
        target = games_dir / gameid
        target.mkdir(parents=True, exist_ok=True)
        (target / "game.conf").write_text(f"name = {gameid}\n")
        return target

    monkeypatch.setattr("miney.env.contentdb.install_game", fake_install)


@pytest.fixture(autouse=True)
def _luanti_dir_in_tmp(tmp_path, monkeypatch):
    """
    Keep every test off the real shared Luanti install.

    ``EnvPaths.luanti_dir`` now defaults to ``~/Luanti`` - one install shared by every
    project on the machine. An ``EnvPaths(root=...)`` built without an explicit
    ``luanti_dir`` would otherwise read and write that real directory, so redirect the
    default into the test's own ``tmp_path``. Tests that pass ``luanti_dir`` explicitly
    override it anyway; this only catches the ones that rely on the default.
    """
    monkeypatch.setattr(
        "miney.env.paths.default_luanti_dir", lambda: tmp_path / "Luanti"
    )
