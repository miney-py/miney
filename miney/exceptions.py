# Luanti exceptions
class MineyRunError(Exception):
    """
    The local ``.miney`` environment could not be used as asked.

    Raised by :class:`~miney.luanti.Luanti` and the ``miney`` command when a world
    cannot be selected unambiguously (none exists, several exist and none was named,
    or a named one is missing) or when starting its server failed. The message always
    names the problem and a command that fixes it.
    """
    pass


class ContentDBError(Exception):
    """
    Errors with/from contentDB
    """
    pass


class LuaError(Exception):
    """
    Error during Lua code execution.
    """
    pass


class LuaResultTimeout(Exception):
    """
    The answer from Lua takes to long.
    """
    pass


class DataError(Exception):
    """
    Malformed data received.
    """
    pass


class AuthenticationError(Exception):
    """
    Authentication error.
    """
    pass


class SessionReconnected(Exception):
    """
    We had to reconnect and reauthenticate.
    """
    pass


# Player exceptions
class PlayerNotFoundError(Exception):
    pass


class PlayerOffline(Exception):
    pass


class NoValidPosition(Exception):
    pass
