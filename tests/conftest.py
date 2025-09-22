"""
Shared pytest fixtures for Miney tests.
"""
from __future__ import annotations
import pytest
from miney.lua import Lua


class _DummyClient:
    """
    Minimal client stub so Lua() can be instantiated without a live connection.
    Only attributes that Lua.__init__ accesses are provided.
    """
    def __init__(self) -> None:
        self.command_handler = None


@pytest.fixture
def lua_for_dumps() -> Lua:
    """
    Provides a Lua instance only for testing Lua.dumps (no server interaction).
    """
    return Lua(_DummyClient())
