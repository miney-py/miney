"""Tests for miney.env.probe."""
import socket
import struct

from miney.env.probe import PROTOCOL_ID, probe_server


class _FakeSocket:
    """A UDP socket that records what was sent and returns a scripted reply."""

    def __init__(self, reply: bytes | None = None, error: Exception | None = None):
        self._reply = reply
        self._error = error
        self.sent: list = []
        self.timeout: float | None = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def settimeout(self, value):
        self.timeout = value

    def sendto(self, data, address):
        self.sent.append((data, address))

    def recvfrom(self, size):
        if self._error is not None:
            raise self._error
        return self._reply, ("127.0.0.1", 30000)


def _reply(first_word: int, extra: int = 10) -> bytes:
    return struct.pack(">I", first_word) + b"\x00" * extra


def test_probe_sends_the_handshake_first_packet(monkeypatch):
    # Protocol id, peer id 0, channel 0 - the exact bytes miney's own client opens with.
    fake = _FakeSocket(reply=_reply(PROTOCOL_ID))
    monkeypatch.setattr(socket, "socket", lambda *a, **k: fake)

    assert probe_server("127.0.0.1", 30000) is True
    sent_data, sent_address = fake.sent[0]
    assert sent_data == struct.pack(">I", PROTOCOL_ID) + struct.pack(">HB", 0, 0)
    assert sent_address == ("127.0.0.1", 30000)


def test_probe_is_true_when_the_reply_echoes_the_protocol_id(monkeypatch):
    # Verified against Luanti 5.16.1: the server's first reply is 14 bytes beginning
    # with the protocol id.
    monkeypatch.setattr(socket, "socket", lambda *a, **k: _FakeSocket(reply=_reply(PROTOCOL_ID)))
    assert probe_server("127.0.0.1", 30000) is True


def test_probe_is_false_when_something_else_answers(monkeypatch):
    # Some unrelated UDP service replying on the port is not a Luanti server.
    monkeypatch.setattr(socket, "socket", lambda *a, **k: _FakeSocket(reply=_reply(0xDEADBEEF)))
    assert probe_server("127.0.0.1", 30000) is False


def test_probe_is_false_on_a_reply_too_short_to_identify(monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *a, **k: _FakeSocket(reply=b"\x01\x02"))
    assert probe_server("127.0.0.1", 30000) is False


def test_probe_is_false_on_timeout(monkeypatch):
    monkeypatch.setattr(socket, "socket", lambda *a, **k: _FakeSocket(error=socket.timeout()))
    assert probe_server("127.0.0.1", 30000) is False


def test_probe_is_false_when_the_port_refuses_the_packet(monkeypatch):
    # A free UDP port on Windows answers sendto with an ICMP unreachable, which recvfrom
    # raises as ConnectionResetError - a subclass of OSError.
    monkeypatch.setattr(socket, "socket", lambda *a, **k: _FakeSocket(error=ConnectionResetError()))
    assert probe_server("127.0.0.1", 30000) is False


def test_probe_sets_the_timeout_it_was_given(monkeypatch):
    fake = _FakeSocket(reply=_reply(PROTOCOL_ID))
    monkeypatch.setattr(socket, "socket", lambda *a, **k: fake)
    probe_server("127.0.0.1", 30000, timeout=0.25)
    assert fake.timeout == 0.25
