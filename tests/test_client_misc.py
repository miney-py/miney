from __future__ import annotations
from miney.luanticlient.client import LuantiClient


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
