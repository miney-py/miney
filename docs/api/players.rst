Players
=======

The ``players`` attribute of the :class:`~miney.Luanti` object provides access to all online players.
It behaves like a list and allows you to get a specific :class:`~miney.player.Player` object by their name.

This is implemented via the :class:`~miney.player.PlayerIterable` class.

:Example:

    >>> # Get a list of all online player names
    >>> lt.players.list()
    ['miney', 'Player2']
    >>>
    >>> # Access a specific player
    >>> p = lt.players.miney
    >>> p.position
    Point(x=10, y=5, z=-20)

.. autoclass:: miney.player.PlayerIterable
   :members:

.. toctree::
   :maxdepth: 1

   player