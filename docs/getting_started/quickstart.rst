Quickstart
==========

Welcome in the sandbox!
-----------------------

Blockgames like Minecraft or Luanti give you the ideal playground for creative playing and building just like a real sandbox.
But other than real sandboxes, you can work on very large worlds together with your friends over the internet.
And you can use (very simplified) physics, save the progress and more.

But what about learning programming while expressing your creativity? Why not automate things? Or build even greater things?


Installation
------------

Windows
^^^^^^^

 * Download the latest Luanti distribution from https://www.luanti.org/downloads/ and extract it to a folder.
 * Start Luanti by running the "luanti.exe" in the "bin" folder.
 * Download the latest Python Version from https://www.python.org/downloads/ and install it.
 * Install miney by opening a command prompt (cmd) and typing:

>>> pip install miney

Linux
^^^^^

 * Download the latest Luanti by following instruction on https://www.luanti.org/downloads/
 * You should have Python 3 installed, if not, install it with your package manager.
 * Install miney by opening a terminal and typing:

>>> pip3 install miney

MacOS
^^^^^

 * Download the latest Luanti by following instruction on https://www.luanti.org/downloads/
 * You should have Python 3 installed, if not, install it with Homebrew or download it from https://www.python.org/downloads/.
 * Install miney by opening a terminal and typing:

>>> pip install miney


For all Plattforms
^^^^^^^^^^^^^^^^^^

 * **Luanti**:
    * Install the Miney mod by starting Luanti and clicking to "Content", "Browse online content" and searching for miney.
 * **Python**:
    * You can install Miney systemwide by typing this in a command prompt: "pip install miney"
    * Suggestion: Make yourself familiar with venv's, so you can isolate different development environments.
      A good starting point is https://docs.python.org/3/tutorial/venv.html

How to start a game
-------------------

* Start Luanti and create a new world.
* Press the "Select Mods" Button, then select "miney" and enable it. Close this screen by pressing "Save".
* Activate the "Host Server" option, so that the miney client (and others) can connect to your game.
* Press "Host Game" to start.
* Run your favorite Python IDE or editor and start coding!


Verify your setup
-----------------

After installing Miney and the Luanti mod, it's a good idea to verify that everything is working together.
The `check_setup.py` script is designed for this purpose. It connects to your Luanti server, performs a few basic actions, and reports whether the connection was successful.

.. dropdown:: View Code (`check_setup.py`)

   .. literalinclude:: ../../examples/check_setup.py
      :language: python
      :linenos:

Just copy the code in a file named `check_setup.py` and open a terminal in the same folder and type this into it:

>>> python check_setup.py
...
2025-08-11 01:03:43 | INFO     | ✅ Verification successful. Miney appears to be correctly set up!
2025-08-11 01:03:44 | INFO     | Disconnecting from server
2025-08-11 01:03:44 | INFO     | Script finished.

This is the best way to confirm your setup before diving into more complex projects. You can find this and other examples in the :doc:`../examples` section.


First lines of code
-------------------

The first lines of code with Miney should be the import statement and the creation of the Miney object "lt" (short for Luanti). This will
connect Miney to your already running Luanti.

::

    import miney

    lt = miney.Luanti()

.. Important::

    Whenever you see a object "lt" in the documentation, it was created with this line!


Interactive Exploration with the Python Shell
---------------------------------------------

Miney is designed to be highly interactive, making it perfect for use in a Python REPL (Read-Eval-Print Loop) or an IDE like IDLE. This allows you to explore the game world and the Miney API without needing to write and run a full script—an excellent way for beginners to learn and experiment.

.. note::

   IDLE is Python's Integrated Development and Learning Environment and is included with every Python installation.
   You can start it from your command line by typing ``python -m idlelib.idle``.

A key feature is dynamic auto-completion. Miney fetches information like node types and online player names from the server and makes them available for tab-completion in modern Python shells.

**Example: Interacting with Players**

You can easily see and interact with online players. Type `lt.players.` in your Python shell and press the `Tab` key. You will see a list of all online players. You can then access a player object directly by their name to get their properties.

.. code-block:: python
   :caption: Example of player completion in a Python REPL

   >>> lt.players.  # Press Tab
   lt.players.miney          lt.players.Netzvamp          lt.players.Player3
   >>>
   >>> lt.players.Player3
   Point(x=-158, y=3, z=-16)

**Example: Discovering Node Types**

Similarly, you can discover all available node types. Type `lt.nodes.names.` and press `Tab`. You'll see a list of all registered node names (e.g., `default:stone`, `flowers:rose`). You can then use these names as strings in functions that manipulate the world.

.. code-block:: python
   :caption: Discovering and using a node name

   >>> from miney import Point
   >>> lt.nodes.names.  # Press Tab
   >>> lt.nodes.names.default.  # Press Tab
   >>> lt.nodes.names.default.apple  # Press Enter
   'default:apple'
   >>> lt.nodes.set(Point(10, 20, 30), lt.nodes.names.default.apple)

This powerful interactive discovery feature significantly lowers the barrier to entry, especially in educational settings, as you can learn and explore what's possible directly within the Python shell.
