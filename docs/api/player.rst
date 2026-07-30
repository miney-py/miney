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


.. rubric:: Moving a player

:meth:`~miney.Player.move` is the one that does all of it — put them somewhere, turn
them, or fly them there over a few seconds while they look at something else. Everything
past the first argument can be left out.

The short names lead back to it, so pick whichever reads better:

.. code-block:: python

   player.teleport(Point(10, 20, 30))          # move(destination=...)
   player.look_at(Point(0, 20, 0))             # move(look_at=...)
   player.fly_to(Point(50, 40, 50), duration=3)  # move(..., smooth=True, duration=3)
   player.turn(yaw=math.pi)                    # move(yaw=...)

.. important::

   A player put in mid-air **falls**, and in some games that is fatal. Use
   :meth:`~miney.Player.hold` before moving them somewhere with nothing under it.

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
