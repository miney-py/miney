from __future__ import annotations
import os
import socket
import subprocess
from pathlib import Path

import miney.env.process as process
from miney.env.discover import LuantiInstall
from miney.env.paths import EnvPaths
from miney.env.process import (
    DEFAULT_PORT,
    client_command,
    find_free_port,
    is_pid_alive,
    is_port_free,
    server_command,
    stop_pid,
)

INSTALL = LuantiInstall(launch=["/opt/luanti"], version=(5, 16, 1), source="path")
FLATPAK = LuantiInstall(
    launch=["flatpak", "run", "--filesystem=/p/.miney", "org.luanti.luanti"],
    version=(5, 16, 1),
    source="flatpak",
)


def test_server_command_passes_world_config_port_and_log(tmp_path: Path):
    paths = EnvPaths(root=tmp_path / ".miney")

    command = server_command(INSTALL, paths, "castle", 30005)

    assert command[0] == "/opt/luanti"
    assert "--server" in command
    assert str(paths.world_dir("castle")) in command
    assert str(paths.config_file) in command
    assert str(paths.log_file("castle")) in command
    assert "30005" in command


def test_server_command_keeps_the_flatpak_prefix_in_front(tmp_path: Path):
    paths = EnvPaths(root=tmp_path / ".miney")

    command = server_command(FLATPAK, paths, "w", DEFAULT_PORT)

    assert command[:4] == FLATPAK.launch
    assert command[4] == "--server"


def test_client_command_connects_and_skips_the_menu(tmp_path: Path):
    paths = EnvPaths(root=tmp_path / ".miney")

    command = client_command(INSTALL, paths, 30005, "Netzvamp")

    assert "--go" in command
    assert "--address" in command
    assert "127.0.0.1" in command
    assert "--name" in command
    assert "Netzvamp" in command
    assert str(paths.client_pw) in command


def test_client_command_never_puts_the_password_in_arguments(tmp_path: Path):
    paths = EnvPaths(root=tmp_path / ".miney")
    paths.client_pw.parent.mkdir(parents=True)
    paths.client_pw.write_text("hunter2", newline="")

    command = client_command(INSTALL, paths, 30005, "Netzvamp")

    assert "--password" not in command
    assert "hunter2" not in command


def test_is_port_free_detects_a_bound_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    try:
        assert is_port_free(port) is False
    finally:
        sock.close()


def test_is_port_free_on_an_unused_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    assert is_port_free(port) is True


def test_find_free_port_skips_a_taken_one(monkeypatch):
    taken = {30000, 30001}
    monkeypatch.setattr(
        "miney.env.process.is_port_free", lambda port, host="127.0.0.1": port not in taken
    )
    assert find_free_port(30000) == 30002


def test_find_free_port_gives_up_after_the_attempt_limit(monkeypatch):
    monkeypatch.setattr(
        "miney.env.process.is_port_free", lambda port, host="127.0.0.1": False
    )
    try:
        find_free_port(30000, attempts=3)
    except OSError as error:
        assert "30000" in str(error)
        assert "30002" in str(error)
    else:
        raise AssertionError("expected OSError")


def test_is_pid_alive_for_this_process():
    assert is_pid_alive(os.getpid()) is True


def test_is_pid_alive_for_none():
    assert is_pid_alive(None) is False


def test_is_pid_alive_for_an_impossible_pid():
    assert is_pid_alive(0) is False


def test_is_pid_alive_survives_a_tasklist_codepage_mismatch(monkeypatch):
    """
    Forces the Windows ``tasklist`` branch of ``is_pid_alive`` on every platform,
    including Ubuntu CI, by monkeypatching ``sys.platform`` as seen from the module
    under test, and replaces ``subprocess.run`` with a fake that faithfully
    reproduces what CPython actually hands back in both cases.

    ``tasklist``'s localized "no matching tasks" message is written in the
    console's OEM codepage (e.g. cp850), while ``subprocess.run(..., text=True)``
    decodes with the ANSI codepage (e.g. cp1252). On non-English Windows those
    differ, and decoding the raw bytes fails inside subprocess's internal reader
    thread -- CPython then hands back a ``CompletedProcess`` whose ``stdout`` is
    ``None``, and ``str(pid) in result.stdout`` crashes with ``TypeError`` instead
    of returning ``False``. Passing ``errors="replace"`` fixes this: the reader
    thread no longer dies, and ``stdout`` becomes the message with a replacement
    character where the undecodable byte was.

    Spawns no process and asserts on the returned value, not merely "did not
    raise", so this test fails against the pre-fix code with the same
    ``TypeError`` the real bug produced, and passes against the fixed code.
    """
    monkeypatch.setattr(process.sys, "platform", "win32")

    def fake_run(command, *, capture_output, text, errors=None, check):
        if errors == "replace":
            # cp850's "INFORMATION: Es werden keine Tasks ausgef\xfchrt, die den
            # Kriterien entsprechen." after a lossy cp1252 decode of the raw bytes.
            stdout = (
                "INFORMATION: Es werden keine Tasks ausgef�hrt, "
                "die den Kriterien entsprechen.\r\n"
            )
        else:
            stdout = None
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(process.subprocess, "run", fake_run)

    assert is_pid_alive(999999) is False


def test_stop_pid_is_false_for_none():
    assert stop_pid(None) is False


def test_game_env_points_every_variant_at_the_games_directory(tmp_path: Path):
    # Verified on Luanti 5.16.1: without one of these, a server whose world.mt names a
    # game outside the installation exits 1 with "Game [] could not be found."
    paths = EnvPaths(root=tmp_path / ".miney")
    paths.games_dir.mkdir(parents=True)

    env = process.game_env(paths)
    assert env is not None
    for name in process.GAME_PATH_VARS:
        assert env[name] == str(paths.games_dir)


def test_game_env_keeps_the_rest_of_the_environment(tmp_path: Path, monkeypatch):
    paths = EnvPaths(root=tmp_path / ".miney")
    paths.games_dir.mkdir(parents=True)
    monkeypatch.setenv("MINEY_TEST_MARKER", "kept")

    env = process.game_env(paths)
    assert env["MINEY_TEST_MARKER"] == "kept"


def test_game_env_is_none_when_there_are_no_games_of_our_own(tmp_path: Path):
    # Nothing to point at means nothing to override; the child inherits ours as-is.
    paths = EnvPaths(root=tmp_path / ".miney")
    assert process.game_env(paths) is None


def test_spawn_detached_passes_the_environment_through(tmp_path: Path, monkeypatch):
    captured = {}

    class FakePopen:
        def __init__(self, command, **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs
            self.pid = 4242

    monkeypatch.setattr(process.subprocess, "Popen", FakePopen)
    pid = process.spawn_detached(["luanti", "--server"], tmp_path, env={"A": "B"})

    assert pid == 4242
    assert captured["kwargs"]["env"] == {"A": "B"}


def test_spawn_detached_without_an_environment_does_not_pass_one(tmp_path: Path, monkeypatch):
    # Passing env=None to Popen means "inherit"; passing env={} would mean "empty", and
    # a server started with an empty environment fails in ways nobody can read.
    captured = {}

    class FakePopen:
        def __init__(self, command, **kwargs):
            captured["kwargs"] = kwargs
            self.pid = 7

    monkeypatch.setattr(process.subprocess, "Popen", FakePopen)
    process.spawn_detached(["luanti"], tmp_path)

    assert captured["kwargs"].get("env") is None
