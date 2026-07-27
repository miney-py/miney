Luanti
======

This is the starting point for this library. Creating a ``Luanti`` object connects you to a Luanti server, and
everything else in Miney hangs off it: the players, the nodes, the chat, the Lua interface. If no server is
running, it starts one for you.

It also carries the settings that belong to the world as a whole, like the time of day.

It takes no arguments. Miney finds the running Luanti by itself — one your project started, or one you
opened from the Luanti menu, singleplayer included — and it does not join the game, so nobody appears in
your world. The one thing it cannot do is reach a Luanti on **another** computer: it talks to the mod
through two files in Luanti's own directory, and a file on your disk is not on somebody else's machine.

:Example:

    >>> import miney
    >>>
    >>> lt = miney.Luanti()
    >>>
    >>> # We set the time to midday.
    >>> lt.time_of_day = 0.5
    >>>
    >>> # Write to the servers log
    >>> lt.log("Time is set to midday ...")

.. seealso::

   :doc:`../getting_started/basics` explains the ``lt`` object for readers who are new to Miney.


.. autoclass:: miney.Luanti
   :members:

.. rubric:: Related Data Structures

.. autoclass:: miney.luanti.GameInfo
   :members:
   :undoc-members:

.. rubric:: API Components

All interaction with the game world starts with the ``Luanti`` object. The following pages document the major classes and components that are accessed through the ``Luanti`` object and its properties.

.. toctree::
   :maxdepth: 3

   assets
   callback
   chat
   lua
   nodes
   players
   point
   storage
   tool
