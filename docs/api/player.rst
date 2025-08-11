Player
======

Represents a player on the server and allows changing their properties like their view, speed, or gravity.
Each player has an :class:`~miney.inventory.Inventory` which can be accessed via the ``inventory`` property.


:Example:
    >>> lt.players.MyPlayer.position
    <<< Point(x=10, y=5, z=-20)


.. autoclass:: miney.Player
   :members:

.. toctree::
   :maxdepth: 1

   inventory
