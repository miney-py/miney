# Minetest exceptions
class MinetestRunError(Exception):
    """
    Error: minetest was not found.
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
