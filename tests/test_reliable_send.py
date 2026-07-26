"""Reliable sending: the window, the retransmission and the giving up.

A packet that is lost gets no acknowledgement, and Luanti deliberately stays silent
about one that arrives too far ahead - `src/network/mtp/threads.cpp`: *"packet is not
within receive window, don't send ack. if this was a valid packet it's gonna be
retransmitted"*. So this is the half of the conversation Miney has to hold up. None of
it is reachable over loopback, where nothing is ever lost.
"""
from __future__ import annotations
import threading
import time

import pytest

from miney.luanticlient import connection as conn_module
from miney.luanticlient.connection import Connection, SEND_WINDOW, MAX_SEND_TRIES
from miney.luanticlient.state import ClientStateHolder


class _FakeSocket:
    """Records what was sent, and can be told to swallow some of it."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.drop = set()          # indices of sendto calls to discard
        self.calls = 0

    def sendto(self, packet, addr):
        self.calls += 1
        if self.calls - 1 not in self.drop:
            self.sent.append(packet)
        return len(packet)


@pytest.fixture
def conn() -> Connection:
    c = Connection("127.0.0.1", 30000, protocol=None, state=ClientStateHolder(),
                   command_processor=lambda *a: None)
    c.sock = _FakeSocket()
    c.running = True
    return c


def _packet(n: int) -> bytes:
    return f"packet-{n}".encode()


def test_a_sent_packet_is_kept_until_it_is_acknowledged(conn):
    assert conn._send_reliable(_packet(1), seqnum=100)
    assert 100 in conn._unacked, "nothing to resend with if it never arrives"

    conn._handle_ack(100)
    assert conn._unacked == {}


def test_an_unacknowledged_packet_is_sent_again(conn):
    conn._send_reliable(_packet(1), seqnum=100)
    assert conn.sock.calls == 1

    conn._resend_expired()
    assert conn.sock.calls == 1, "not before the timeout is up"

    conn._unacked[100].sent_at -= conn_module.RESEND_TIMEOUT + 0.01
    conn._resend_expired()
    assert conn.sock.calls == 2
    assert conn.sock.sent[-1] == _packet(1), "resent verbatim, same sequence number"


def test_an_acknowledged_packet_is_never_sent_again(conn):
    conn._send_reliable(_packet(1), seqnum=100)
    conn._handle_ack(100)

    conn._resend_expired()
    assert conn.sock.calls == 1


def test_it_gives_up_rather_than_resending_for_ever(conn):
    conn._send_reliable(_packet(1), seqnum=100)

    for _ in range(MAX_SEND_TRIES + 2):
        if 100 in conn._unacked:
            conn._unacked[100].sent_at -= conn_module.RESEND_TIMEOUT + 0.01
        conn._resend_expired()

    assert conn._unacked == {}, "a lost packet must not wedge the window for ever"
    assert conn.sock.calls == MAX_SEND_TRIES


def test_the_window_blocks_until_an_acknowledgement_arrives(conn):
    for seqnum in range(SEND_WINDOW):
        assert conn._send_reliable(_packet(seqnum), seqnum)
    assert len(conn._unacked) == SEND_WINDOW

    done = threading.Event()

    def send_one_more():
        conn._send_reliable(_packet(999), seqnum=999)
        done.set()

    waiter = threading.Thread(target=send_one_more, daemon=True)
    waiter.start()

    assert not done.wait(timeout=0.3), "a full window has to wait"
    conn._handle_ack(0)
    assert done.wait(timeout=2.0), "and go again as soon as a slot is free"
    waiter.join(timeout=1.0)

    assert 999 in conn._unacked


def test_a_stopped_receiver_releases_a_blocked_sender(conn):
    """Otherwise disconnecting during a big upload would hang on the window."""
    for seqnum in range(SEND_WINDOW):
        conn._send_reliable(_packet(seqnum), seqnum)

    result = []
    waiter = threading.Thread(
        target=lambda: result.append(conn._send_reliable(_packet(999), 999)),
        daemon=True)
    waiter.start()
    time.sleep(0.15)

    conn.running = False
    with conn._unacked_cond:
        conn._unacked_cond.notify_all()

    waiter.join(timeout=2.0)
    assert result == [False], "the send reports failure instead of blocking for ever"


def test_waiting_for_acks_returns_when_the_queue_empties(conn):
    conn._send_reliable(_packet(1), seqnum=100)

    threading.Timer(0.1, lambda: conn._handle_ack(100)).start()
    t0 = time.monotonic()
    conn._wait_for_acks(timeout=5.0)

    assert conn._unacked == {}
    assert time.monotonic() - t0 < 4.0, "it waited for the timeout instead of the ACK"


def test_waiting_for_acks_gives_up_on_time(conn):
    conn._send_reliable(_packet(1), seqnum=100)

    t0 = time.monotonic()
    conn._wait_for_acks(timeout=0.2)
    elapsed = time.monotonic() - t0

    assert 0.15 < elapsed < 2.0, f"waited {elapsed:.2f}s for a 0.2s timeout"
