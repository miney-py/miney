Code Examples
=============

This section contains practical examples demonstrating how to use the Miney library.
The code is included directly from the source files, so it's always up-to-date.

Setup Checker (`check_setup.py`)
--------------------------------

This script is the best starting point to verify that your Miney installation and server connection are working correctly.

.. dropdown:: View Code

   .. literalinclude:: ../examples/check_setup.py
      :language: python
      :linenos:

Lua Console (`luaconsole.py`)
-----------------------------

A powerful, interactive Read-Eval-Print Loop (REPL) for executing Lua code on the server directly from your terminal.

.. dropdown:: View Code

   .. literalinclude:: ../examples/luaconsole.py
      :language: python
      :linenos:

Treasure Hunt Game (`treasure_hunt.py`)
---------------------------------------

A complete, multiplayer treasure hunt game that showcases many of Miney's features in action, including world interaction and player management.

.. dropdown:: View Code

   .. literalinclude:: ../examples/treasure_hunt.py
      :language: python
      :linenos:

Chat Callbacks (`chat.py`)
--------------------------

A compact example of non-blocking chat callbacks. It shows how to subscribe to chat messages
and register a simple chat command that is processed by the Python client.

.. dropdown:: View Code

   .. literalinclude:: ../examples/chat.py
      :language: python
      :linenos:

Move Showcase (`move_showcase.py`)
----------------------------------

Demonstrates smooth, scripted player movements using the Player.move() API.

.. dropdown:: View Code

   .. literalinclude:: ../examples/move_showcase.py
      :language: python
      :linenos:

Choreography Showcase (`choreography.py`)
----------------------------------------

Demonstrates a multi-client solar-system choreography using multiple Luanti clients with Player.move(). Ensure the server is running. Clients will connect as 'dancer_1' to 'dancer_<N>'. On first connection, you may need to grant them 'miney' and 'noclip' privileges.

.. dropdown:: View Code

   .. literalinclude:: ../examples/choreography.py
      :language: python
      :linenos:
