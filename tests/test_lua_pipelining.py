"""
Commands that are sent without waiting for their answer.

This is what keeps a ``for`` loop usable on the file channel: the mod runs every
complete line it finds in one server step, so a thousand commands cost one step instead
of a thousand. Measured against a real server, 400 node placements went from 12.2 s to
0.43 s. The price is that an error surfaces later than the line that caused it, which is
most of what these tests are about.
"""
from __future__ import annotations

import pytest

from conftest import FakeTransport
from miney.exceptions import LuaError, LuaResultTimeout
from miney.lua import Lua, MAX_IN_FLIGHT


class Answering(FakeTransport):
    """
    A transport that answers every request, and fails the ones it is told to.

    :param fail_on: Lua sources that should come back as an error.
    """

    def __init__(self, fail_on: set[str] | None = None):
        super().__init__()
        self.fail_on = fail_on or set()

    def send(self, fields: dict) -> bool:
        super().send(fields)
        execution_id = fields.get("execution_id")
        if fields.get("lua") in self.fail_on:
            self.deliver({"execution_id": execution_id, "error": "Runtime error: boom"})
        else:
            self.deliver({"execution_id": execution_id, "result": fields.get("lua")})
        return True


class Silent(FakeTransport):
    """A transport that takes requests and never answers any of them."""

    def send(self, fields: dict) -> bool:
        return super().send(fields)


def test_wait_false_returns_at_once_and_sends():
    transport = Answering()
    lua = Lua(transport)

    assert lua.run("return 1", wait=False) is None
    assert transport.sent[0]["lua"] == "return 1"


def test_a_later_waiting_call_clears_what_went_before():
    """
    The mod answers in the order it was asked, so an answer proves the earlier ones in.

    Nothing is left pending afterwards - a loop that leaked one entry per iteration
    would be a slow memory leak nobody would connect to Miney.
    """
    transport = Answering()
    lua = Lua(transport)

    for i in range(5):
        lua.run(f"return {i}", wait=False)
    assert len(lua._in_flight) == 5

    assert lua.run("return 'last'") == "return 'last'"
    assert lua._in_flight == []
    assert lua.pending_lua_results == {}


def test_an_error_from_a_sent_on_command_is_raised_at_the_next_call():
    transport = Answering(fail_on={"broken"})
    lua = Lua(transport)

    lua.run("broken", wait=False)          # this is the line the message must name
    broken_line = test_an_error_from_a_sent_on_command_is_raised_at_the_next_call

    with pytest.raises(LuaError) as error:
        lua.run("return 1")

    message = str(error.value)
    assert "boom" in message
    assert "Miney had already sent on" in message
    assert __file__.split("\\")[-1].split("/")[-1] in message
    assert 'lua.run("broken", wait=False)' in message
    assert broken_line is not None  # keeps the name above from looking unused


def test_the_error_wins_over_the_result_of_the_call_that_found_it():
    transport = Answering(fail_on={"broken"})
    lua = Lua(transport)

    lua.run("broken", wait=False)
    with pytest.raises(LuaError):
        lua.run("return 1")

    # And the failure is not raised a second time by the next call.
    assert lua.run("return 2") == "return 2"


def test_flush_waits_and_raises():
    transport = Answering(fail_on={"broken"})
    lua = Lua(transport)

    lua.run("fine", wait=False)
    lua.run("broken", wait=False)

    with pytest.raises(LuaError, match="boom"):
        lua.flush()
    assert lua._in_flight == []


def test_flush_with_nothing_outstanding_does_nothing():
    transport = Answering()
    lua = Lua(transport)
    lua.flush()
    assert transport.sent == []


def test_a_loop_that_never_waits_is_capped():
    """
    Sending without waiting has to stop somewhere.

    A loop with no end would otherwise queue for ever: memory here, and a request log
    on the server that grows until the disk is full.
    """
    transport = Answering()
    lua = Lua(transport)

    for i in range(MAX_IN_FLIGHT + 10):
        lua.run(f"return {i}", wait=False)

    # Only the ten sent since the cap fired are still open, and nothing else is left
    # behind: everything before them was collected.
    assert len(lua._in_flight) == 10
    assert set(lua.pending_lua_results) == {one for one, _ in lua._in_flight}


def test_a_timeout_does_not_blame_the_next_call():
    """
    When the server goes quiet, everything in flight is of unknown fate.

    Holding on to it would make the call after the timeout raise for commands that may
    well have run, so it is dropped instead.
    """
    transport = Silent()
    lua = Lua(transport)

    lua.run("earlier", wait=False)
    with pytest.raises(LuaResultTimeout):
        lua.run("return 1", timeout=0.02)

    assert lua._in_flight == []
    assert lua.pending_lua_results == {}


def test_nothing_is_left_pending_after_a_barrier():
    """
    Every answer is taken off, whether anybody was waiting for it or not.

    A leak here would be one dict per loop iteration, growing until the script ends.
    """
    transport = Answering()
    lua = Lua(transport)

    lua.run("a", wait=False)
    lua.run("b", wait=False)
    lua.run("return 1")

    assert len(transport.sent) == 3
    assert lua.pending_lua_results == {}
