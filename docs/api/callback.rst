========
Callback
========

Manages event and chat command registrations with the server.

The ``Callback`` object is accessed through the ``callbacks`` property of the :class:`~miney.luanti.Luanti` object.

Watching a place
================

.. code-block:: python

    from miney import Point

    @lt.callbacks.on("player_near", {"pos": Point(10, 20, 30), "radius": 5})
    def treasure(event):
        lt.chat.send_to_player(event.player_name, "You found it!")

It fires when somebody *arrives*, once — not for every moment they stand there. Walking
out and back in fires it again.

.. important::

   ``radius`` has no default. There is no number that is right for everybody, and one
   that is too large is a handler that goes off for the whole map.

.. autoclass:: miney.callback.Callback
   :members: