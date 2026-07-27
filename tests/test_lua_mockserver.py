"""
:class:`~miney.lua.Lua` against a transport that answers like the mod does.

This used to emulate the client protocol packet by packet, because that was the only
way a request reached the server. Now a transport is "here is a dict, there is a dict",
and the fake below is short enough to read in one go - which is most of the point of
having replaced the transport at all.
"""
from __future__ import annotations
import pathlib
import pytest

from conftest import FakeTransport
from miney.lua import Lua, REQUIRED_MOD_API


class MockTransport(FakeTransport):
    """
    A transport that answers a request the moment it is sent.

    :param mode: ``success``, ``error``, or ``noop`` for a server that never answers.
    """

    def __init__(self, mode: str = "success", connected: bool = True,
                 mod_api: int | None = REQUIRED_MOD_API):
        super().__init__(mod_api=mod_api, connected=connected)
        self.mode = mode

    def send(self, fields: dict) -> bool:
        super().send(fields)
        execution_id = fields.get("execution_id")
        if self.mode == "noop":
            return True
        if self.mode == "success":
            self.deliver({"execution_id": execution_id, "result": 42})
        elif self.mode == "error":
            self.deliver({"execution_id": execution_id, "error": "boom"})
        else:
            raise ValueError(f"Unknown mock mode: {self.mode}")
        return True


def test_run_returns_the_result():
    assert Lua(MockTransport()).run("return 1") == 42


def test_run_regular_error_raises():
    with pytest.raises(Exception) as exc:
        Lua(MockTransport(mode="error")).run("return 0")
    assert "boom" in str(exc.value)


def test_run_refuses_a_mod_from_before_the_handshake():
    """The failure this replaces was a nil index inside the user's own Lua."""
    transport = MockTransport(mod_api=None)

    with pytest.raises(Exception) as exc:
        Lua(transport).run("return 1")
    message = str(exc.value)
    assert "too old" in message
    assert "miney upgrade" in message
    assert not transport.sent  # refused before any code went out


def test_run_refuses_a_mod_that_is_behind():
    transport = MockTransport(mod_api=REQUIRED_MOD_API - 1)

    with pytest.raises(Exception) as exc:
        Lua(transport).run("return 1")
    assert f"speaks version {REQUIRED_MOD_API - 1}" in str(exc.value)


def test_run_accepts_a_newer_mod():
    """A mod ahead of us still speaks what we know, so it must not be refused."""
    assert Lua(MockTransport(mod_api=REQUIRED_MOD_API + 5)).run("return 1") == 42


def test_a_request_goes_out_whole_however_long_it_is():
    """
    8 MB crossed the file channel in a single server step, so there is nothing to cut.

    The formspec transport had a 640K ceiling per submit and the splitting that went
    with it. Both are gone, and a request that arrived in pieces would need the mod to
    reassemble it again.
    """
    transport = MockTransport()

    assert Lua(transport).run("--" + "x" * (2 * 1024 * 1024)) == 42
    assert len(transport.sent) == 1


def test_run_refuses_code_over_the_absolute_maximum():
    """
    The mod refuses a longer line too (MAX_REQUEST in init.lua), so saying no here
    turns a dropped request into a sentence that names the problem.
    """
    from miney.lua import MAX_LUA_SOURCE

    transport = MockTransport()
    lua = Lua(transport)

    with pytest.raises(Exception) as exc:
        lua.run("--" + "x" * (MAX_LUA_SOURCE + 1))
    assert "too long to send" in str(exc.value)
    assert not lua.pending_lua_results
    assert not transport.sent


def test_run_timeout_says_what_to_check():
    transport = MockTransport(mode="noop")

    with pytest.raises(Exception) as exc:
        Lua(transport).run("return 0", timeout=0.02)
    message = str(exc.value)
    assert "did not answer within 0.02 seconds" in message
    assert transport.timeout_hint() in message


def test_run_not_connected_raises():
    with pytest.raises(Exception) as exc:
        Lua(MockTransport(connected=False)).run("return 0")
    assert "Not connected" in str(exc.value)


def test_get_node_info_builds_lua_for_specific_and_all():
    transport = MockTransport()
    lua = Lua(transport)

    lua.get_node_info("default:stone")
    lua.get_node_info()

    sent_codes = [entry["lua"] for entry in transport.sent]
    assert sent_codes[0] == 'return dump(minetest.registered_nodes["default:stone"])'
    assert "minetest.registered_nodes" in sent_codes[1]
    assert "count =" in sent_codes[1]
    assert "names =" in sent_codes[1]


def test_run_file_uses_contents(tmp_path: pathlib.Path):
    transport = MockTransport()
    lua = Lua(transport)

    script = tmp_path / "snippet.lua"
    script.write_text("return 5", encoding="utf-8")

    assert lua.run_file(str(script)) == 42  # the mock answers 42 whatever it is given
    assert any(entry["lua"] == "return 5" for entry in transport.sent)
