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

    The server answered, but not with something Miney could make sense of - for
    instance a region read that describes a different number of nodes than were asked
    for. It means the two halves disagree, so the usual cause is a mod that is not the
    one this Miney ships with.
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
class PlayerNotFoundError(IndexError):
    """
    There is no player of that name.

    Raised by ``lt.players["Name"]`` and by :class:`~miney.player.Player` itself. The
    message lists who *is* online, because that is nearly always the next question::

        >>> lt.players["Steev"]
        PlayerNotFoundError: There is no player 'Steev'. Online: 'Steve', 'Ana'.

    It stays a subclass of ``IndexError``, which is what an unknown name used to raise.
    """
    pass


class PlayerOffline(Exception):
    """
    The player exists, but is not currently connected.

    Their account is known to the server - Miney can read their privileges - but
    anything that needs them to be in the world, such as
    :attr:`~miney.Player.position`, has nothing to work with.
    """
    pass


class NoValidPosition(Exception):
    """
    A position was asked for that does not exist in the world.
    """
    pass
