"""
How Miney reaches the Luanti server.

The Lua mod keeps an append-only log in Luanti's own ``mod_data`` directory, one for
each direction, and moves everything across on the server step. This module is the
other end of it. There is no account, no port, no password and nothing to configure:
if a server with the Miney mod is running on this computer, the beacon it wrote says
where its channel is, and appending a line to that channel runs Lua on it.

That also covers the case no network client can reach. A singleplayer world started
from the Luanti menu refuses a second client outright
(``serverpackethandler.cpp:152-158``), and a file is not a client.

Nothing in here is part of the public API. :class:`~miney.luanti.Luanti` opens the
channel, and the words "channel", "session" and "offset" never reach a script.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .exceptions import MineyRunError
# The module, not the function: the test suite redirects `default_luanti_dir` away from
# a real home directory by patching it there, and a name bound here at import time
# would not see that.
from .env import paths as env_paths

logger = logging.getLogger(__name__)

#: Environment variables that move Luanti's user directory, in the order the engine
#: reads them (``porting.cpp:172-180``). The second one is deprecated and still honoured.
USER_PATH_VARS = ("LUANTI_USER_PATH", "MINETEST_USER_PATH")

#: How often the reader thread looks for new answers. The floor for a round-trip is the
#: server step - 17 ms in a game you are standing in, 31 on a world ``miney start``
#: launched - so polling faster than this buys nothing and this fast costs a ``stat``.
POLL_INTERVAL = 0.005

#: How often a session says it is still there. The mod forgets a session that has been
#: quiet for 30 seconds, and forgetting means cancelling its timers and dropping its
#: chat commands, so this has to be comfortably inside that.
PING_INTERVAL = 5.0


# One world has one request log, so two Miney scripts on the same world append to the
# same file. Linux makes that safe on its own: an `O_APPEND` write to a regular file
# picks its offset and writes under the same lock, so it cannot be split or landed on.
# Windows only pretends to - its C runtime implements append as a seek to the end
# followed by a write, and nothing holds those two together. Two processes can therefore
# choose the same offset and the second one writes over the first.
#
# What that costs was measured with the test below, 300 requests of 20 KB from two
# processes: on Linux 300 arrive with this lock removed, three runs out of three. On
# Windows 282 arrive and 18 are simply gone - not damaged, not short, absent, along with
# every byte of them. The script that sent them waits out its timeout for an answer to a
# request the server never saw, and the seam where the overwrite lands leaves one line
# the mod cannot parse either.
#
# Hence a real lock, taken around every write. It lives on a file of its own and never
# on `c2s`: Windows file locks are mandatory rather than advisory, so a range locked on
# the request log would make the mod's own read of it fail - the opposite of the point.
if sys.platform == "win32":
    import msvcrt

    def _lock(handle) -> None:
        """
        Take the channel's write lock, waiting for whoever has it.

        :param handle: The open lock file.
        """
        handle.seek(0)
        # LK_LOCK retries for ten seconds and then raises, which is the right shape:
        # the lock is held for the length of one write, so anything near that long is
        # a stuck process rather than contention, and the caller turns it into a
        # logged failure instead of writing into the middle of somebody else's line.
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)

    def _unlock(handle) -> None:
        """
        Give the write lock back.

        :param handle: The open lock file.
        """
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(handle) -> None:
        """
        Take the channel's write lock, waiting for whoever has it.

        :param handle: The open lock file.
        """
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)

    def _unlock(handle) -> None:
        """
        Give the write lock back.

        :param handle: The open lock file.
        """
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _platform_user_path() -> Path | None:
    """
    Where a system-wide Luanti keeps its user directory on this platform.

    Read out of ``porting.cpp``: ``%APPDATA%\\Minetest`` on Windows,
    ``~/.minetest`` on Linux and ``~/Library/Application Support/minetest`` on macOS.
    The directory is still called *minetest* on all three - the rename has not reached
    it yet - which is exactly the kind of thing worth not guessing.

    :return: The directory, or None if the platform is unknown.
    """
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        return Path(appdata) / "Minetest" if appdata else None
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "minetest"
    return Path.home() / ".minetest"


def candidate_user_paths(luanti_dir: Path | None = None) -> list[Path]:
    """
    Every directory a running Luanti might be using as its user path.

    In the engine's own order: the environment variables first, then the Luanti that
    Miney downloads - which is portable, so its user path is the install directory
    itself - and finally the place a Luanti installed by the system would use.

    :param luanti_dir: The Miney-managed install, if one is known. Defaults to
        :func:`~miney.env.paths.default_luanti_dir`.
    :return: The candidates, most specific first, without duplicates.
    """
    found: list[Path] = []
    for variable in USER_PATH_VARS:
        value = os.environ.get(variable)
        if value:
            found.append(Path(value))
    found.append(luanti_dir or env_paths.default_luanti_dir())
    system = _platform_user_path()
    if system:
        found.append(system)

    unique: list[Path] = []
    for path in found:
        if path not in unique:
            unique.append(path)
    return unique


@dataclass(frozen=True)
class Beacon:
    """
    What a running server says about itself in ``beacon.json``.

    Written once when the mod loads and removed when the server shuts down properly.
    A server that was killed leaves it behind, and there is no process id in it to
    check against - the Lua sandbox has none to offer - so a beacon means "a server
    was here", not "a server is here". Liveness is probed, never read.

    :param directory: The channel directory this beacon was found in.
    :param mod_api: The mod's contract version, compared against
        :data:`~miney.lua.REQUIRED_MOD_API`.
    :param engine: The Luanti version string, e.g. ``"5.16.1"``.
    :param world: Full path of the world the server is running.
    :param world_name: Just the world's directory name.
    :param singleplayer: True when the server is a singleplayer game rather than a
        dedicated one.
    :param started: Unix time the mod loaded.
    """

    directory: Path
    mod_api: int
    engine: str
    world: str
    world_name: str
    singleplayer: bool
    started: int

    def __repr__(self) -> str:
        return f'<Miney channel for world "{self.world_name}" ({self.engine})>'


def read_beacon(path: Path) -> Beacon | None:
    """
    Read one ``beacon.json``.

    :param path: The file to read.
    :return: The beacon, or None if it is missing or not readable as one.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or "mod_api" not in data:
        return None
    return Beacon(
        directory=path.parent,
        mod_api=int(data.get("mod_api", 0)),
        engine=str(data.get("engine", "")),
        world=str(data.get("world", "")),
        world_name=str(data.get("world_name", "")),
        singleplayer=bool(data.get("singleplayer", False)),
        started=int(data.get("started", 0)),
    )


def find_beacons(luanti_dir: Path | None = None) -> list[Beacon]:
    """
    Every Miney channel on this computer, newest first.

    One world can have one channel, and a computer can have several worlds up at once -
    the world a project started and one the user opened from the Luanti menu - so this
    can return more than one. :class:`~miney.luanti.Luanti` says so rather than picking.

    :param luanti_dir: The Miney-managed install, if one is known.
    :return: The beacons found, the most recently started one first.
    """
    beacons: list[Beacon] = []
    seen: set[Path] = set()
    for user_path in candidate_user_paths(luanti_dir):
        root = user_path / "mod_data" / "miney"
        if not root.is_dir():
            continue
        for entry in sorted(root.iterdir()):
            beacon_file = entry / "beacon.json"
            if entry.resolve() in seen or not beacon_file.is_file():
                continue
            seen.add(entry.resolve())
            beacon = read_beacon(beacon_file)
            if beacon is not None:
                beacons.append(beacon)
    beacons.sort(key=lambda one: one.started, reverse=True)
    return beacons


class FileChannel:
    """
    One session on one world's channel.

    Reached through :class:`~miney.luanti.Luanti`, never built by hand. It offers two
    things - send a field table, hear about the dictionaries that come back - and hides
    the fact that both are lines in a file.

    There is no size limit to know about: 8 MB crossed the channel in a single server
    step, indistinguishable from a kilobyte.

    :param directory: The channel directory, from a :class:`Beacon`.
    :param timeout: How long :meth:`attach` waits for the server to answer.
    """

    def __init__(self, directory: Path, timeout: float = 10.0):
        self.directory = Path(directory)
        #: Which contract version the mod on the other end speaks. Known before the
        #: first command here, because the answer to the session's hello carries it.
        self.mod_api: int | None = None
        self._session = str(uuid.uuid4())
        self._listeners: list[Callable[[dict], None]] = []
        self._send_lock = threading.Lock()
        self._running = True
        self._reader: threading.Thread | None = None
        self._last_ping = 0.0

        c2s = self.directory / "c2s"
        s2c = self.directory / "s2c"
        try:
            # Created rather than assumed: the mod makes both files while it loads, but
            # a beacon can outlive a wiped directory and a missing file must not become
            # a traceback three frames deep in a thread.
            c2s.touch(exist_ok=True)
            s2c.touch(exist_ok=True)
            self._out = open(c2s, "ab", buffering=0)
            self._in = open(s2c, "rb")
            # Never read or written, only locked. It exists so that the lock has
            # somewhere to live that the mod does not touch.
            self._lock_file = open(self.directory / "lock", "ab", buffering=0)
        except OSError as error:
            raise MineyRunError(
                f"Miney found a Luanti server at {self.directory} but cannot write to "
                f"its channel: {error}"
            ) from error

        # Start at the end of what is already there. Everything before this belongs to
        # a session that has ended, and replaying it would answer requests nobody made.
        self._offset = s2c.stat().st_size

        self.attach(timeout)

    # -- attaching ---------------------------------------------------------------

    def attach(self, timeout: float) -> None:
        """
        Announce the session and wait for the server to answer it.

        The lone newline is not decoration. A Python process killed halfway through a
        write leaves a line without its terminator, and the mod is waiting for that
        terminator before it reads anything further. Sending one turns the remains into
        a single unparseable record, which the mod logs and drops, instead of letting
        it be spliced onto the front of the first real request.

        :param timeout: Seconds to wait for the answer.
        :raises MineyRunError: If nothing answers in time.
        """
        acknowledged = threading.Event()

        def note(record: dict) -> None:
            if record.get("action") == "hello":
                acknowledged.set()

        self._listeners.append(note)
        self._reader = threading.Thread(
            target=self._read_loop, name="miney-channel-reader", daemon=True
        )
        self._reader.start()

        self._raw_write(b"\n")
        self._raw_send({"session": self._session, "op": "hello"})

        if not acknowledged.wait(timeout):
            self.close()
            raise MineyRunError(
                f"A Luanti server left its mark in {self.directory}, but it did not "
                f"answer within {timeout:.0f} seconds.\n"
                f"{self.timeout_hint()}"
            )
        self._listeners.remove(note)

    def timeout_hint(self) -> str:
        """
        What to tell somebody whose command went unanswered.

        Two things look exactly alike from here, and the likely one comes first. A
        singleplayer game with the menu open is not running at all: the server returns
        immediately at ``dtime == 0`` (``server.cpp:684-685``), so no mod code runs,
        no timer fires and nothing arrives until the menu closes. It is invisible from
        the outside, and pressing ESC to go back to the editor is the most ordinary
        thing a beginner does.

        :return: A sentence naming both possibilities and what to do about them.
        """
        return (
            "If the game is open in a window, check whether it is paused - a "
            "singleplayer world stops completely while the ESC menu is up, and nothing "
            "Miney sends is looked at until you close it. Otherwise the server is no "
            "longer running and has to be started again."
        )

    # -- the transport interface -------------------------------------------------

    @property
    def connected(self) -> bool:
        """Whether this session is still usable."""
        return self._running

    def add_listener(self, listener: Callable[[dict], None]) -> None:
        """
        Hear about every answer and every event the server sends.

        :param listener: Called with each decoded record, on the reader thread.
        """
        self._listeners.append(listener)

    def send(self, fields: dict[str, str]) -> bool:
        """
        Send one request.

        :param fields: The request.
        :return: True if it was written.
        """
        return self._raw_send({"session": self._session, "fields": fields})

    def close(self) -> None:
        """
        End the session and let the server clean up after it straight away.

        Without the goodbye the mod waits out its own timeout before cancelling
        whatever timers and chat commands this session left behind, which is half a
        minute of a script that has ended still doing things.
        """
        if not self._running:
            return
        try:
            self._raw_send({"session": self._session, "op": "bye"})
        except Exception:  # noqa: BLE001 - shutting down, nothing left to tell
            pass
        self._running = False
        if self._reader is not None and self._reader.is_alive():
            self._reader.join(timeout=1.0)
        for handle in (self._out, self._in, self._lock_file):
            try:
                handle.close()
            except OSError:
                pass

    # -- the machinery ------------------------------------------------------------

    def _raw_send(self, record: dict[str, Any]) -> bool:
        """
        Write one record as a line.

        :param record: What to send.
        :return: True if it was written.
        """
        return self._raw_write(
            json.dumps(record, ensure_ascii=False).encode("utf-8") + b"\n"
        )

    def _raw_write(self, blob: bytes) -> bool:
        """
        Put bytes on the request log, whoever else is writing to it.

        Two locks, and both are needed. The threading one keeps this process's own
        threads apart - the reader sends pings from its own thread while the main one
        sends commands. The file lock keeps *other* Miney processes apart, which is a
        different problem with a different answer; see the comment on :func:`_lock`.

        :param blob: The bytes to append, terminator included.
        :return: True if they were written.
        """
        try:
            with self._send_lock:
                _lock(self._lock_file)
                try:
                    self._out.write(blob)
                finally:
                    _unlock(self._lock_file)
        except OSError as error:
            logger.error("Could not write to the Miney channel: %s", error)
            return False
        return True

    def _read_loop(self) -> None:
        """Watch the answer log and hand every complete line to the listeners."""
        partial = b""
        while self._running:
            try:
                size = os.fstat(self._in.fileno()).st_size
                if size < self._offset:
                    # The answer log got shorter than what has already been read, so a
                    # server restarted and emptied it. Reading on from the old offset
                    # would land inside a record.
                    self._offset = 0
                    partial = b""
                if size > self._offset:
                    self._in.seek(self._offset)
                    chunk = self._in.read(size - self._offset)
                    self._offset += len(chunk)
                    partial += chunk
                    # A trailing fragment is not a short record, it is not a record
                    # yet. Keeping it costs one buffer and makes a torn read impossible
                    # rather than merely unlikely.
                    *lines, partial = partial.split(b"\n")
                    for line in lines:
                        self._deliver(line)
            except (OSError, ValueError) as error:
                # ValueError is close() winning the race against this thread's next
                # read, which is an ordinary shutdown and not worth a line in the log.
                if self._running:
                    logger.error("The Miney channel stopped being readable: %s", error)
                self._running = False
                return

            now = time.monotonic()
            if now - self._last_ping > PING_INTERVAL:
                self._last_ping = now
                self._raw_send({"session": self._session, "op": "ping"})
            time.sleep(POLL_INTERVAL)

    def _deliver(self, line: bytes) -> None:
        """
        Decode one line and give it to whoever is listening.

        :param line: One record, without its terminator.
        """
        if not line.strip():
            return
        try:
            record = json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            logger.warning("Ignored an unreadable answer from the server.")
            return
        if not isinstance(record, dict) or record.get("session") != self._session:
            return
        data = record.get("data")
        if not isinstance(data, dict):
            return
        if "mod_api" in data:
            self.mod_api = data["mod_api"]
        for listener in list(self._listeners):
            try:
                listener(data)
            except Exception as error:  # noqa: BLE001 - a broken listener is not fatal
                logger.error("Error handling a server answer: %s", error, exc_info=True)

    def __repr__(self) -> str:
        return f'<Miney file channel "{self.directory.name}">'
