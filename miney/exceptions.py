# Luanti exceptions
class MineyRunError(Exception):
    """
    Error: Luanti was not found.
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
class PlayerInvalid(Exception):
    pass


class PlayerOffline(Exception):
    pass


class NoValidPosition(Exception):
    pass
