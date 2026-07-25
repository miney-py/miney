Luanti
======

This is the starting point for this library. Creating a ``Luanti`` object connects you to a Luanti server, and
everything else in Miney hangs off it: the players, the nodes, the chat, the Lua interface. If no server is
running, it starts one for you.

It also carries the settings that belong to the world as a whole, like the time of day.

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

   callback
   chat
   lua
   nodes
   players
   point
   storage
   tool
