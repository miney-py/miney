Code Examples
=============

Working programs, from a few lines to a complete game. The code below is included straight from the source
files, so it is always up to date.

.. important::

   These files are **not** part of the installed package. Get them from the
   `examples folder on GitHub <https://github.com/miney-py/miney/tree/master/examples>`_ — click a file,
   then the download or copy button — and save them into your ``miney-world`` folder next to your own code.

Start a world with ``uv run miney start``, then run an example the same way you run your own scripts:

.. code-block:: text

   uv run treasure_hunt.py

They are ordered from short to ambitious. Read them, run them, then change a number and run them again —
that is where the learning happens.


💬 Chat Callbacks (`chat.py`)
------------------------------

The shortest of the bunch. It subscribes to chat messages and registers a chat command that your Python
answers, without blocking your program while it waits.

.. dropdown:: View Code

   .. literalinclude:: ../examples/chat.py
      :language: python
      :linenos:


⌨️ Lua Console (`luaconsole.py`)
---------------------------------

An interactive prompt that sends Lua straight to the server and prints what comes back. Useful when you want
to poke at the game engine directly, and a compact example of a read-eval-print loop.

.. dropdown:: View Code

   .. literalinclude:: ../examples/luaconsole.py
      :language: python
      :linenos:


🏃 Move Showcase (`move_showcase.py`)
--------------------------------------

Smooth, scripted player movement with :meth:`~miney.Player.move` — walking a path, looking at a target,
timing the steps.

.. dropdown:: View Code

   .. literalinclude:: ../examples/move_showcase.py
      :language: python
      :linenos:


🗺️ Treasure Hunt Game (`treasure_hunt.py`)
-------------------------------------------

A complete multiplayer game in one file. It builds terrain, tracks players, reacts to chat and keeps score —
the best place to see how the pieces fit together.

.. dropdown:: View Code

   .. literalinclude:: ../examples/treasure_hunt.py
      :language: python
      :linenos:


🪐 Choreography Showcase (`choreography.py`)
---------------------------------------------

The ambitious one: several Luanti clients at once, moved like a solar system.

The clients connect as ``dancer_1`` up to ``dancer_<N>``, so your server has to be running before you start
it. The first time each dancer connects, grant it the ``miney`` and ``noclip`` privileges.

.. dropdown:: View Code

   .. literalinclude:: ../examples/choreography.py
      :language: python
      :linenos:
