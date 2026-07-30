Sky
===

Light is the cheapest way to change how a world feels, and the only one that costs no
blocks at all. ``player.sky`` is the colour above a player, the clouds, the sun, the
moon, the stars and how bright everything looks.

Every one of them belongs to one player, because that is how Luanti works - there is no
sky the whole server shares. Changing it for everybody is a loop:

.. code-block:: python

    for player in lt.players:
        player.sky.color = "#101040"

Start here
----------

    >>> p = lt.players.Steve
    >>> p.sky.color = "#101040"

One line, and the blue sky is gone. What is left is a flat colour that stays that way
at noon and at midnight. Set it back to ``None`` and the game paints its own sky again.

Night at noon
-------------

The colour alone changes what is above the player. What makes it *feel* like night is
the brightness:

.. code-block:: python

    p.sky.color = "#101040"
    p.sky.brightness = 0.05     # 0 is night, 1 is noon
    p.sky.clouds = False
    p.sky.sun = False
    p.sky.stars = True

The stars are there in daylight too, only far too faint to see. Turning the brightness
down is what brings them out.

.. important::

   **This is what one player sees, not what the world is.** Luanti keeps every one of
   these settings per player and sends it to that one client. The world carries on in
   broad daylight: plants grow the same, torches burn the same, and **nothing spawns**
   because a player's sky went dark.

   .. code-block:: python

       p.sky.brightness = 0.05   # Steve sees night. The world is still noon.
       lt.time_of_day = 0.0      # This is the one that brings the zombies.

Putting it back
---------------

.. warning::

   A sky stays the way you left it, long after the script has ended. A player left in
   an artificial night is in it until they log out.

   :meth:`~miney.Sky.reset` is the way back, and it belongs at the end of anything that
   changed the sky:

   .. code-block:: python

       p.sky.reset()

Games that paint their own sky
------------------------------

VoxeLibre repaints every player's sky about once a second — that is how rain darkens
the day, how the Nether glows red and how everything goes green under water. Left to
itself it would paint over your colour before the next line of your script ran.

Miney's mod joins that game's own chain of sky filters, as the last link, and lays what
you have set over what the game just decided:

* it happens **for this player only** — everybody else keeps their weather;
* the parts you have not set stay the game's, so the fog and the sunset colours behind
  your clouds carry on changing;
* :meth:`~miney.Sky.reset` drops the whole overlay and the game has its player back.

Games with no sky mod of their own — Minetest Game among them — never notice any of
this, and nothing in your script changes either way.

.. autoclass:: miney.Sky
   :members:
