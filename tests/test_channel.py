"""
The file channel, offline.

It is tested against a fake mod: a function that reads the request log
and appends to the answer log, which is all the Lua side does. No server is started and
no packet is built - that is the whole reason this transport was worth having.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from miney.channel import (
    Beacon,
    FileChannel,
    candidate_user_paths,
    find_beacons,
    read_beacon,
)
from miney.exceptions import MineyRunError


class FakeMod:
    """
    The Lua half, in Python: read complete lines from ``c2s``, answer on ``s2c``.

    Deliberately written the way ``channel.lua`` is - a held offset, one snapshot per
    tick, and a line without its terminator left alone - because those are the parts
    that can go wrong.

    :param directory: The channel directory to serve.
    """

    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "c2s").touch()
        (directory / "s2c").touch()
        self.requests = open(directory / "c2s", "rb")
        self.answers = open(directory / "s2c", "ab", buffering=0)
        self.offset = 0
        self.seen: list[dict] = []
        self.bad = 0
        self.gone: list[str] = []
        self.compactions = 0
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while self._running:
            self.tick()
            time.sleep(0.002)

    def tick(self) -> None:
        size = os.fstat(self.requests.fileno()).st_size
        if size < self.offset:
            self.offset = 0
            self.answers.close()
            open(self.directory / "s2c", "wb").close()
            self.answers = open(self.directory / "s2c", "ab", buffering=0)
            self.compactions += 1
        if size == self.offset:
            return
        self.requests.seek(self.offset)
        chunk = self.requests.read(size - self.offset)
        used = 0
        while True:
            stop = chunk.find(b"\n", used)
            if stop == -1:
                break
            self._record(chunk[used:stop])
            used = stop + 1
        self.offset += used

    def _record(self, line: bytes) -> None:
        # What a client sends when it attaches, to close off a record some earlier
        # process died halfway through. Nothing arrived and nothing is wrong, and the
        # real mod skips it for the same reason (``channel.lua:142``).
        if not line.strip():
            return
        try:
            record = json.loads(line)
        except ValueError:
            self.bad += 1
            return
        session = record.get("session")
        if record.get("op") == "hello":
            self.reply(session, {"ok": True, "action": "hello", "mod_api": 7})
            return
        if record.get("op") == "bye":
            self.gone.append(session)
            return
        if record.get("op") == "ping":
            return
        self.seen.append(record)
        fields = record.get("fields") or {}
        if fields.get("execution_id"):
            self.reply(session, {"execution_id": fields["execution_id"], "result": 42})

    def reply(self, session: str, data: dict) -> None:
        line = json.dumps({"session": session, "data": data}).encode() + b"\n"
        self.answers.write(line)

    def stop(self) -> None:
        self._running = False
        self._thread.join(timeout=1)
        self.requests.close()
        self.answers.close()


@pytest.fixture
def served(tmp_path):
    """A channel directory with a fake mod answering on it."""
    directory = tmp_path / "world-1234abcd"
    mod = FakeMod(directory)
    yield directory, mod
    mod.stop()


def test_attach_and_round_trip(served):
    directory, mod = served
    channel = FileChannel(directory, timeout=5)
    try:
        assert channel.connected
        assert channel.mod_api == 7

        answers: list[dict] = []
        channel.add_listener(answers.append)
        channel.send({"lua": "return 1", "execute": "true", "execution_id": "abc"})

        deadline = time.time() + 5
        while not answers and time.time() < deadline:
            time.sleep(0.005)
        assert answers == [{"execution_id": "abc", "result": 42}]
    finally:
        channel.close()

    # The goodbye is a line in a file, so the mod sees it on its next tick, not at the
    # instant close() returns.
    deadline = time.time() + 5
    while not mod.gone and time.time() < deadline:
        time.sleep(0.005)
    assert mod.gone == [channel._session]


def test_attach_terminates_a_line_a_dead_process_left_behind(served):
    """
    A Python killed mid-write leaves a request without its newline.

    The mod is waiting for that newline before it looks at anything further, so the
    fragment would otherwise be spliced onto the front of the next real request and
    run as somebody else's code. Attaching sends one newline to close it off.
    """
    directory, mod = served
    (directory / "c2s").write_bytes(b'{"session": "old", "fields": {"lua": "os.exi')

    channel = FileChannel(directory, timeout=5)
    try:
        deadline = time.time() + 5
        while mod.bad == 0 and time.time() < deadline:
            time.sleep(0.005)
        assert mod.bad == 1, "the fragment must be rejected as one unparseable record"

        # And the session still works afterwards.
        answers: list[dict] = []
        channel.add_listener(answers.append)
        channel.send({"lua": "return 1", "execute": "true", "execution_id": "x"})
        deadline = time.time() + 5
        while not answers and time.time() < deadline:
            time.sleep(0.005)
        assert answers[0]["result"] == 42
    finally:
        channel.close()


def test_answers_from_an_earlier_session_are_not_replayed(served):
    """
    The log outlives the process that wrote it.

    Starting at the end of what is there is what keeps a second run from answering
    requests the first one made.
    """
    directory, mod = served
    mod.reply("someone-else", {"execution_id": "stale", "result": 1})
    time.sleep(0.02)

    channel = FileChannel(directory, timeout=5)
    try:
        seen: list[dict] = []
        channel.add_listener(seen.append)
        time.sleep(0.05)
        assert seen == []
    finally:
        channel.close()


def test_a_record_split_across_two_writes_waits_for_its_newline(served):
    """A half-written answer is not a short answer, it is not an answer yet."""
    directory, mod = served
    channel = FileChannel(directory, timeout=5)
    try:
        seen: list[dict] = []
        channel.add_listener(seen.append)

        line = json.dumps({
            "session": channel._session,
            "data": {"execution_id": "split", "result": 7},
        }).encode()
        with open(directory / "s2c", "ab", buffering=0) as handle:
            handle.write(line[:20])
            time.sleep(0.05)
            assert seen == [], "nothing may be delivered before the terminator"
            handle.write(line[20:] + b"\n")

        deadline = time.time() + 5
        while not seen and time.time() < deadline:
            time.sleep(0.005)
        assert seen == [{"execution_id": "split", "result": 7}]
    finally:
        channel.close()


def test_answers_for_another_session_are_ignored(served):
    directory, mod = served
    channel = FileChannel(directory, timeout=5)
    try:
        seen: list[dict] = []
        channel.add_listener(seen.append)
        mod.reply("somebody-else", {"execution_id": "nope", "result": 1})
        time.sleep(0.05)
        assert seen == []
    finally:
        channel.close()


def test_an_answer_log_that_was_emptied_is_read_from_the_beginning(served):
    """
    The mod empties both logs when its server starts, so a restart shortens the file.

    Reading on from the old offset would land in the middle of a record, and a torn
    read is the one failure this design is supposed to be incapable of.
    """
    directory, mod = served
    channel = FileChannel(directory, timeout=5)
    try:
        seen: list[dict] = []
        channel.add_listener(seen.append)

        channel.send({"lua": "return 1", "execute": "true", "execution_id": "before"})
        deadline = time.time() + 5
        while not seen and time.time() < deadline:
            time.sleep(0.005)
        assert seen[0]["execution_id"] == "before"

        # What a server restart looks like from here.
        mod.answers.close()
        open(directory / "s2c", "wb").close()
        mod.answers = open(directory / "s2c", "ab", buffering=0)
        mod.reply(channel._session, {"execution_id": "after", "result": 1})

        deadline = time.time() + 5
        while len(seen) < 2 and time.time() < deadline:
            time.sleep(0.005)
        assert seen[1]["execution_id"] == "after"
    finally:
        channel.close()


#: A second Miney process, sending large requests to the same channel as fast as it can.
#: Large on purpose: a write of a few hundred bytes is atomic everywhere, and the whole
#: question is what happens above that.
WRITER = """
import sys, time
from pathlib import Path
from miney.channel import FileChannel

directory, tag, count = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
channel = FileChannel(directory, timeout=15)

# Attaching takes a moment, and two processes that never overlap prove nothing. Both
# say they are ready and wait for the same starting gun, so they are inside the write
# loop at the same time whatever the machine was doing when they started.
(directory / ("ready-" + tag)).touch()
while not (directory / "go").exists():
    time.sleep(0.005)

payload = tag * 20000
for number in range(count):
    channel.send({
        "lua": payload, "execute": "true", "execution_id": tag + str(number),
    })
channel.close()
"""


def test_two_processes_can_write_to_one_channel(served):
    """
    Two scripts on one world, and neither one's request comes out damaged.

    One world has one ``c2s``, so a second script appends to the same file as the
    first. On Linux that is safe by itself - ``O_APPEND`` picks the offset and writes
    under one lock - but Windows appends by seeking to the end and then writing, and
    two processes can pick the same end. Without the lock this loses 18 of the 300
    requests below on Windows and none of them on Linux.

    So the failure this guards against is silent on the sending side - the request
    never reaches the server and the script waits out its timeout - which is why it
    is worth two subprocesses to catch. ``mod.seen`` is the real assertion: a request
    that was written over is missing from it rather than damaged.
    """
    directory, mod = served
    each = 150
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", WRITER, str(directory), tag, str(each)],
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        for tag in ("a", "b")
    ]
    deadline = time.time() + 60
    while not all((directory / f"ready-{tag}").exists() for tag in "ab"):
        assert time.time() < deadline, "a writer never attached to the channel"
        time.sleep(0.01)
    (directory / "go").touch()

    for process in processes:
        assert process.wait(timeout=120) == 0

    deadline = time.time() + 10
    while len(mod.seen) < 2 * each and time.time() < deadline:
        time.sleep(0.01)

    assert mod.bad == 0, f"{mod.bad} requests came out of the channel damaged"
    assert len(mod.seen) == 2 * each
    assert {record["fields"]["execution_id"][0] for record in mod.seen} == {"a", "b"}


def test_attach_to_a_dead_server_says_what_to_check(tmp_path):
    directory = tmp_path / "dead-0000"
    directory.mkdir()

    with pytest.raises(MineyRunError) as error:
        FileChannel(directory, timeout=0.2)
    message = str(error.value)
    assert "did not answer" in message
    assert "paused" in message


# -- discovery ------------------------------------------------------------------


def _write_beacon(directory: Path, **overrides) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    data = {
        "mod_api": 7,
        "engine": "5.16.1",
        "world": str(directory),
        "world_name": directory.name.rsplit("-", 1)[0],
        "singleplayer": True,
        "started": 100,
    }
    data.update(overrides)
    path = directory / "beacon.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_read_beacon(tmp_path):
    path = _write_beacon(tmp_path / "mine-abcd1234")
    beacon = read_beacon(path)
    assert isinstance(beacon, Beacon)
    assert beacon.world_name == "mine"
    assert beacon.engine == "5.16.1"
    assert "mine" in repr(beacon)


def test_read_beacon_survives_rubbish(tmp_path):
    path = tmp_path / "beacon.json"
    path.write_text("not json at all", encoding="utf-8")
    assert read_beacon(path) is None
    assert read_beacon(tmp_path / "missing.json") is None


def test_find_beacons_newest_first(tmp_path, monkeypatch):
    monkeypatch.setenv("LUANTI_USER_PATH", str(tmp_path))
    root = tmp_path / "mod_data" / "miney"
    _write_beacon(root / "old-11111111", started=10)
    _write_beacon(root / "new-22222222", started=20)

    beacons = find_beacons()
    assert [one.world_name for one in beacons] == ["new", "old"]


def test_find_beacons_without_a_mod_data_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("LUANTI_USER_PATH", str(tmp_path))
    assert find_beacons() == []


def test_candidate_user_paths_puts_the_environment_first(tmp_path, monkeypatch):
    monkeypatch.setenv("LUANTI_USER_PATH", str(tmp_path / "explicit"))
    paths = candidate_user_paths(luanti_dir=tmp_path / "managed")
    assert paths[0] == tmp_path / "explicit"
    assert tmp_path / "managed" in paths
