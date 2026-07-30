Entities
========

Everything in the world that is not a block: a cow, a zombie, a boat, a pickaxe
somebody dropped. Miney could not see any of it before ``lt.entities``.

Start here
----------

.. code-block:: python

    player = lt.players[0]

    for thing in lt.entities.near(player.position, radius=20):
        print(thing)

.. code-block:: text

    <Luanti Entity "mobs_mc:cow" at (12, 8, -3)>
    <Luanti Entity "__builtin:item" at (9, 8, 1)>

Every answer is a list, so a ``for`` loop over it is a program that does something to
each one — and a list that is empty is a perfectly good answer, read with ``if``:

.. code-block:: python

    if lt.entities.near(player.position, radius=5):
        lt.chat.send_to_player(player.name, "Something is close.")

Where are the players?
----------------------

Nowhere, unless you ask:

.. code-block:: python

    lt.entities.near(player.position, radius=20, players=True)

.. important::

   A player is always within any radius of themselves, so leaving people out is the
   default. Asking *"what is near me"* and finding yourself in the answer is a
   surprise in the wrong place.

A snapshot, not a leash
-----------------------

What you get back is where things stood **when you asked**. The cow walks on. Ask
again rather than keeping one around.

.. autoclass:: miney.Entities
   :members:

.. autoclass:: miney.Entity
   :members:
