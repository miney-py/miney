Players
=======

The ``players`` attribute of the :class:`~miney.Luanti` object provides access to all online players.
It behaves like a list — you can iterate over it, count it and index it — and every player is also reachable
by name, which is what makes ``lt.players.`` plus :kbd:`Tab` work in the Python shell.

This is implemented via the :class:`~miney.player.PlayerIterable` class.

:Example:

    >>> # See who is online
    >>> lt.players
    <Players: ['miney', 'Player2']>
    >>> len(lt.players)
    2
    >>>
    >>> # Access a specific player by name ...
    >>> lt.players.miney
    <Luanti Player "miney">
    >>>
    >>> # ... or by position in the list
    >>> lt.players[0].position
    <Luanti Point(x=10.0, y=5.0, z=-20.0)>
    >>>
    >>> # Iterating gives you Player objects
    >>> for player in lt.players:
    ...     print(player.name, player.hp)

.. autoclass:: miney.player.PlayerIterable
   :members:

.. toctree::
   :maxdepth: 1

   player