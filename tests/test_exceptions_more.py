from __future__ import annotations
import pytest

from miney import exceptions as mex
from miney.luanticlient import exceptions as lex


def test_miney_domain_exceptions_str_and_init():
    cases = [
        mex.MineyRunError("run failed"),
        mex.ContentDBError("content db unreachable"),
        mex.LuaError("lua err"),
        mex.LuaResultTimeout("timeout"),
        mex.DataError("bad data"),
        mex.AuthenticationError("auth failed"),
        mex.SessionReconnected("reconnected"),
        mex.PlayerNotFoundError("player not found"),
        mex.PlayerOffline("player offline"),
        mex.NoValidPosition("no valid position"),
    ]
    for exc in cases:
        s = str(exc)
        assert isinstance(s, str)
        assert s  # non-empty


def test_luanti_client_exceptions():
    e = lex.LuantiConnectionError("denied", reason_code=1)
    assert "denied" in str(e)
    assert getattr(e, "reason_code", None) == 1

    p = lex.LuantiPermissionError("perm")
    assert "perm" in str(p)
