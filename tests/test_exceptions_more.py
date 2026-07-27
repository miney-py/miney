from __future__ import annotations

import miney
from miney import exceptions as mex


def test_miney_domain_exceptions_str_and_init():
    cases = [
        mex.MineyRunError("run failed"),
        mex.ContentDBError("content db unreachable"),
        mex.LuaError("lua err"),
        mex.LuaResultTimeout("timeout"),
        mex.LuantiConnectionError("no channel"),
        mex.DataError("bad data"),
        mex.AssetError("refused"),
        mex.AssetTimeout("never arrived"),
        mex.HudElementGone("gone"),
        mex.PlayerNotFoundError("player not found"),
        mex.PlayerOffline("player offline"),
        mex.NoValidPosition("no valid position"),
    ]
    for exc in cases:
        s = str(exc)
        assert isinstance(s, str)
        assert s  # non-empty


def test_every_exception_is_reachable_as_miney_something():
    """
    ``docs/api/exceptions.rst`` promises they are importable straight from ``miney``.

    Autodoc reads the class out of ``miney.exceptions`` either way, so a name that was
    added there and never re-exported looks documented and is not.
    """
    names = [
        name for name, value in vars(mex).items()
        if isinstance(value, type) and issubclass(value, Exception)
    ]
    assert names
    for name in names:
        assert getattr(miney, name, None) is getattr(mex, name), name
        assert name in miney.__all__, name
