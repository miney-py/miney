Player
======

Represents a player on the server and allows changing their properties like their view, speed, or gravity.
Each player has an :class:`~miney.inventory.Inventory` which can be accessed via the ``inventory`` property.


You never create a ``Player`` yourself — you get one from :doc:`lt.players <players>`.

:Example:

    >>> player = lt.players.miney
    >>> player.position
    <Luanti Point(x=10.0, y=5.0, z=-20.0)>
    >>> player.hp = 20
    >>> player.fly = True


.. autoclass:: miney.Player
   :members:

.. rubric:: Privileges

:attr:`~miney.Player.privileges` gives you the player's Luanti privileges as something that behaves like a
list — you can test with ``in``, ``append`` and ``remove``. Most of the time you do not need it: properties
like :attr:`~miney.Player.fly` and :attr:`~miney.Player.creative` set the right privileges for you.

.. autoclass:: miney.player.PrivilegeManager
   :members:

.. toctree::
   :maxdepth: 1

   hud
   inventory
   player_storage
   sky
