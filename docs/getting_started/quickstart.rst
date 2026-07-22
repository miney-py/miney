Quickstart
==========

* `PyPI <https://pypi.org/project/miney/>`_

* `Luanti ContentDB <https://content.luanti.org/packages/Miney/miney/>`_

Welcome in the sandbox!
-----------------------

Blockgames like Luanti or Minecraft give you the ideal playground for creative playing and building just like a real sandbox.
But other than real sandboxes, you can work on very large worlds together with your friends over the internet.
And you can use (very simplified) physics, save the progress and more.

But what about learning programming while expressing your creativity? Why not automate things? Or build even greater things?

Installation
------------

Miney consists of two parts: the **Luanti mod**, which lets Miney talk to the game, and the **Python library**, which
you write your code against. You need both.

There are four short steps. If you already have Python and know your way around it, jump to
:ref:`Install with pip instead <already-have-python>`.


Step 1: Install uv
^^^^^^^^^^^^^^^^^^

``uv`` is the tool we use to install Python and Miney. It is a single small program and needs no administrator rights.

.. tab-set::

   .. tab-item:: Windows

      Open PowerShell (press the Windows key, type ``powershell``, press Enter) and paste this line:

      .. code-block:: powershell

         powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

   .. tab-item:: Linux & macOS

      Open a terminal and paste this line:

      .. code-block:: bash

         curl -LsSf https://astral.sh/uv/install.sh | sh

.. important::

   **Close your terminal window and open a new one now.**

   The installer adds ``uv`` to your search path, but a window that is already open does not notice the change.
   In the new window, type ``uv --version``. If you see a version number, you are ready.

.. dropdown:: What is uv, and why do we use it?
   :icon: question

   ``uv`` installs Python for you, keeps each of your projects separate, and downloads libraries like Miney.
   It replaces a handful of tools you would otherwise have to learn first (``python.org`` installer, ``pip``,
   ``venv``).

   We recommend it because it removes the three things that most often stop beginners before they write a single
   line of code:

   * **No Python installation puzzle.** ``uv`` downloads Python itself, into your user folder, without
     administrator rights. Nothing on your system is changed or overwritten.
   * **No "externally managed environment" error.** On current Linux distributions and on macOS with Homebrew,
     the plain ``pip install miney`` fails with exactly that message. ``uv`` does not run into it.
   * **No virtual environment ceremony.** You get one, but you never have to activate it.

   ``uv`` is not required to use Miney — it is a normal Python package. See
   :ref:`Install with pip instead <already-have-python>` if you prefer your own setup.


Step 2: Install Luanti and the Miney mod
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. tab-set::

   .. tab-item:: Windows

      Download the latest Luanti from https://www.luanti.org/downloads/ and extract it to a folder.
      Start it by running ``luanti.exe`` in the ``bin`` folder.

   .. tab-item:: Linux

      Follow the instructions for your distribution on https://www.luanti.org/downloads/.

   .. tab-item:: macOS

      Follow the macOS instructions on https://www.luanti.org/downloads/.

With Luanti running, install the mod from inside the game:

* Click **Content**, then **Browse online content**.
* Search for **miney** and install it.

Step 3: Create a folder for your code
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In your new terminal window:

.. code-block:: text

   mkdir miney-world
   cd miney-world
   uv venv
   uv pip install miney

``uv venv`` creates a folder named ``.venv`` next to your code. That is where Miney gets installed, so it stays
separate from everything else on your computer. If you have no Python yet, ``uv`` downloads a current version at
this point — this takes a moment and only happens once.

.. dropdown:: What is that ``.venv`` folder?
   :icon: question

   A *virtual environment*: a private Python installation belonging to this one project. Libraries you install
   here cannot break another project, and another project cannot break this one.

   You never have to activate or even open it — ``uv run`` (next step) finds it on its own. If you delete the
   folder, ``uv venv`` and ``uv pip install miney`` recreate it.

Step 4: Run your code with ``uv run``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Save your Python file in the ``miney-world`` folder and start it like this:

.. code-block:: text

   uv run world.py

.. warning::

   Start your scripts with ``uv run world.py``, **not** with ``python world.py``.

   Only ``uv run`` knows about the ``.venv`` folder from step 3. Plain ``python`` either does not exist yet or is
   a different Python that has never heard of Miney, and you get ``ModuleNotFoundError: No module named 'miney'``.

.. dropdown:: On Windows, ``python`` may open the Microsoft Store
   :icon: alert

   Windows ships a placeholder named ``python.exe``. If you have never installed Python from python.org, typing
   ``python`` opens the Microsoft Store instead of starting Python — even though ``uv`` just downloaded a perfectly
   good Python for you.

   That Python lives in your user folder and is deliberately kept out of your search path, so that it cannot
   interfere with anything else on your system. ``uv run`` addresses it directly. This is why every command in
   this documentation starts with ``uv run``.

.. _already-have-python:

.. dropdown:: Already have Python? Install with pip instead
   :icon: tools

   Miney is a normal package on PyPI and needs **Python 3.10 or newer**:

   .. code-block:: text

      python -m venv .venv
      .venv\Scripts\activate      # Windows
      source .venv/bin/activate   # Linux and macOS
      pip install miney

   Then run your scripts with ``python world.py`` as usual, and read every ``uv run python`` in this
   documentation as plain ``python``.

   If ``pip install`` fails with ``error: externally-managed-environment``, your system Python is protected
   against direct installation. Create the virtual environment as shown above, or use ``uv``.


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

Copy the code into a file named ``check_setup.py`` inside your ``miney-world`` folder, make sure your Luanti world
is running, and start it:

.. code-block:: text

   uv run check_setup.py

.. code-block:: text

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

Start the interactive shell from your ``miney-world`` folder with:

.. code-block:: text

   uv run python

.. note::

   IDLE is Python's Integrated Development and Learning Environment and is included with every Python installation.
   Start it with ``uv run python -m idlelib.idle``.

A key feature is dynamic auto-completion. Miney fetches information like node types and online player names from the server and makes them available for tab-completion in modern Python shells.

**Example: Interacting with Players**

You can easily see and interact with online players. Type `lt.players.` in your Python shell and press the `Tab` key. You will see a list of all online players. You can then access a player object directly by their name to get their properties.

.. code-block:: python
   :caption: Example of player completion in a Python REPL

   >>> lt.players.  # Press Tab
   lt.players.miney          lt.players.HumanPlayer          lt.players.Player3
   >>>
   >>> lt.players.HumanPlayer
   <Luanti Player "HumanPlayer">
   >>> lt.players.HumanPlayer.position
   <Luanti Point(x=-145.0, y=6.0, z=-243.0)>

**Example: Discovering Node Types**

Similarly, you can discover all available node types. Type `lt.nodes.names.` and press `Tab`. You'll see a list of all registered node names (e.g., `default:stone`, `flowers:rose`). You can then use these names as strings in functions that manipulate the world.

.. code-block:: python
   :caption: Discovering and using a node name

   >>> from miney import Node
   >>> lt.nodes.names.  # Press Tab
   >>> lt.nodes.names.default.  # Press Tab
   >>> lt.nodes.names.default.apple  # Press Enter
   'default:apple'
   >>> lt.nodes.set(Node(10, 20, 30, name=lt.nodes.names.default.apple))

This powerful interactive discovery feature significantly lowers the barrier to entry, especially in educational settings, as you can learn and explore what's possible directly within the Python shell.
