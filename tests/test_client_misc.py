from __future__ import annotations
import logging

from miney.luanticlient.client import LuantiClient
from miney.luanticlient.constants import ClientState


def test_client_get_access_denied_reason_and_disconnect():
    client = LuantiClient(playername="Tester", password="pw")
    reason = client.get_access_denied_reason(1)
    assert isinstance(reason, str)
    assert len(reason) > 0
    # No connection established; disconnect should be safe
    client.disconnect()


def test_multiple_denied_reasons_and_idempotent_disconnect():
    client = LuantiClient(playername="Tester", password="pw")
    for code in (0, 1, 2, 3, 4, 5):
        reason = client.get_access_denied_reason(code)
        assert isinstance(reason, str)
        assert reason != ""
    client.disconnect()
    client.disconnect()  # idempotent


def test_unknown_denied_reason_code_returns_string():
    client = LuantiClient(playername="Tester", password="pw")
    msg = client.get_access_denied_reason(9999)
    assert isinstance(msg, str) and msg != ""


# --- being denied access ------------------------------------------------------------


def _denied(state: int, data: bytes = bytes([1])) -> LuantiClient:
    """A client that has just been told 'access denied' while in a given state."""
    client = LuantiClient(playername="Tester", password="pw")
    client.state.state = state
    client.command_handler._handle_access_denied(data)
    return client


def test_a_denial_is_recorded_rather_than_raised():
    # The handler runs on the receiver thread, where nothing can catch an exception:
    # raising there only ever reached the loop's own catch-all, which logged a full
    # traceback at the user. connect() reads the recorded state instead, and that is
    # what turns a denial into an exception on the thread that asked for it.
    client = _denied(ClientState.CONNECTING)

    assert client.state.access_denied_code == 1
    assert client.state.access_denied_reason
    assert client.state.state == ClientState.DISCONNECTED


def test_a_denial_while_connecting_is_not_shouted_about(caplog):
    # Reason code 1 during a first connect means "register first", which Luanti() then
    # does. It is the normal path for every new player, so it must not reach a beginner
    # as an error - connect() raises with the same message for whoever actually cares.
    with caplog.at_level(logging.DEBUG, logger="miney.luanticlient.command_handler"):
        _denied(ClientState.CONNECTING)

    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []


def test_being_denied_after_joining_is_reported(caplog):
    # Not part of any connect: the server dropped a session that was already running.
    # Nobody polls the state for that, so the log is the only channel it has left.
    with caplog.at_level(logging.DEBUG, logger="miney.luanticlient.command_handler"):
        _denied(ClientState.JOINED)

    loud = [record for record in caplog.records if record.levelno >= logging.WARNING]
    assert loud, "a session dropped mid-game has to be reported somewhere"
    assert not any(record.exc_info for record in loud), "a kick is not a Miney bug"
