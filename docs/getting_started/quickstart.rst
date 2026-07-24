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

You need two things: **Luanti**, the game Miney drives, and the **Python library** you write your code against.
You install the library, and Miney brings Luanti along — you do not download or set up the game yourself.

There are three short steps. If you already have Python and know your way around it, jump to
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


Step 2: Create a folder for your code
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

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


Step 3: Start Luanti
^^^^^^^^^^^^^^^^^^^^

One command downloads Luanti, installs the Miney mod, creates a world and opens it on your screen:

.. code-block:: text

   uv run miney start

The very first time, it asks which game your world should use:

.. code-block:: text

   Which game should your world use?

     1) Minetest Game - the calm building sandbox. No monsters or hunger - just you and
        the blocks. Every example in the Miney docs uses its block names.
     2) VoxeLibre (mineclone2) - a Minecraft-like world with mobs, hunger and crafting.
        More to explore, but its block names differ, so the doc examples will not match.

   Enter 1 or 2 [1]:

Press **1** (or just Enter) to follow along with this documentation. Pick **2** if you would rather have a world
with monsters and hunger — just remember the block names in the examples are written for Minetest Game. You only
answer this once; after that the command opens your world straight away.

Then it gets to work, telling you about each step:

.. code-block:: text

   No Luanti found. Downloading v5.16.1 into ~/Luanti...
   Luanti 5.16.1 is ready.
   Downloading Minetest Game from ContentDB...
   Minetest Game installed.
   Downloading VoxeLibre (mineclone2) from ContentDB...
   VoxeLibre (mineclone2) installed.
   Environment ready in .miney.
   World 'minetest_game' uses Minetest Game.
   Started Luanti server for 'minetest_game' on port 30000.
   Opened your client as 'miney'.
   Log: .miney/worlds/minetest_game/server.log
   Your world is open. The server keeps running in the background, so closing the game window does not stop it.
   Stop it when you are done: uv run miney stop

A Luanti window opens with your world. Two things were set up, in two places:

* **Luanti itself and its games** went into a plain ``Luanti`` folder in your home directory. It is an ordinary
  Luanti install you could even start on its own, and every Miney project on this machine shares it — so it is
  downloaded only once, no matter how many projects you make.
* **Your world, its settings and the Miney mod** went into the ``.miney`` folder next to your code. Delete the
  project folder and that world is gone; the shared Luanti in your home directory stays for your other projects.

Later runs skip the downloads and open the world straight away.

The **server keeps running in the background** even after you close the game window — that is what lets your Python
scripts connect to it. When you are done, stop it with ``uv run miney stop``.

Leave this world running for now. In the next step you write Python that connects to it and watches your changes
appear.

.. note::

   The server listens on ``127.0.0.1`` (this machine only), so nobody else on your network can reach your world
   and Windows does not raise a firewall prompt for it.

.. dropdown:: Useful things ``miney`` can do
   :icon: terminal

   Every command starts with ``uv run`` so it uses the Python in your ``.venv``:

   * ``uv run miney status`` — what is installed and what is running.
   * ``uv run miney stop`` — stop the server and close the window.
   * ``uv run miney logs -f`` — watch the server log live.
   * ``uv run miney start --help`` — all options.

.. dropdown:: Want a different game than Minetest Game?
   :icon: package

   ``miney start`` uses `Minetest Game <https://content.luanti.org/packages/Minetest/minetest_game/>`_, and so
   does every example in this documentation. VoxeLibre (``mineclone2``) is downloaded alongside it, so switching to
   it is instant — no second download:

   .. code-block:: text

      uv run miney start --game mineclone2

   .. warning::

      VoxeLibre (``mineclone2``) uses **different node names** than Minetest Game — ``mcl_core:dirt`` instead of
      ``default:dirt``, and so on. The documentation examples assume Minetest Game, so start there while you are
      learning and explore other games once you know your way around.

.. dropdown:: One command from nothing at all
   :icon: rocket

   If you are comfortable running an install script, this single line does everything on this page — installs
   ``uv``, creates the project, installs Miney and starts a world — in one go. Paste it into a **new, empty
   folder**.

   .. tab-set::

      .. tab-item:: Windows

         .. code-block:: powershell

            powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex; $env:Path = \"$HOME\.local\bin;$env:Path\"; uv venv; uv pip install miney; uv run miney start"

      .. tab-item:: Linux & macOS

         .. code-block:: bash

            curl -LsSf https://astral.sh/uv/install.sh | sh \
              && export PATH="$HOME/.local/bin:$PATH" \
              && uv venv && uv pip install miney && uv run miney start

   Only paste commands you understand — that goes double for a line that downloads and launches a game engine.
   The step-by-step route above is the same thing, one command at a time, and stays the recommended way in.

.. dropdown:: On Linux, Miney cannot download Luanti for you
   :icon: alert

   There is no ready-to-run Luanti download for Linux the way there is for Windows and macOS, so Miney cannot
   fetch it. ``uv run miney start`` will stop once and print the exact command for your system — usually your
   package manager or Flatpak, for example:

   .. code-block:: text

      sudo apt install luanti      # Debian/Ubuntu
      flatpak install flathub org.luanti.luanti

   Install Luanti that way, then run ``uv run miney start`` again. From there everything is the same as on
   Windows and macOS — Miney finds your Luanti and takes over.

.. dropdown:: I already run my own Luanti server
   :icon: server

   You do not have to let Miney manage Luanti. If you run a server yourself, install the Miney mod in it and
   Miney connects to it instead:

   * Start Luanti, click **Content**, then **Browse online content**, search for **miney** and install it.
   * Create a world, enable the **miney** mod under **Select Mods**, turn on **Host Server**, and press
     **Host Game**.
   * Point Miney at it with ``miney.Luanti("127.0.0.1")`` (see :doc:`../api/Luanti`), or set ``autostart=False``
     so Miney never starts a server of its own.


Step 4: Run your code with ``uv run``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Save your Python file in the ``miney-world`` folder and start it like this:

.. code-block:: text

   uv run world.py

.. warning::

   Start your scripts with ``uv run world.py``, **not** with ``python world.py``.

   Only ``uv run`` knows about the ``.venv`` folder from step 2. Plain ``python`` either does not exist yet or is
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
      miney start

   Then run your scripts with ``python world.py`` as usual, and read every ``uv run`` in this documentation as
   plain ``python`` (or drop the ``uv run`` prefix from ``miney`` commands).

   If ``pip install`` fails with ``error: externally-managed-environment``, your system Python is protected
   against direct installation. Create the virtual environment as shown above, or use ``uv``.


Verify your setup
-----------------

With your world from step 3 still open, it is a good idea to confirm that Python and Luanti really talk to each
other. The ``check_setup.py`` script does exactly that: it connects to your server, performs a few basic actions,
and reports whether it worked.

.. dropdown:: View Code (`check_setup.py`)

   .. literalinclude:: ../../examples/check_setup.py
      :language: python
      :linenos:

Copy the code into a file named ``check_setup.py`` inside your ``miney-world`` folder and start it:

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
connect Miney to the world you started with ``miney start``.

::

    import miney

    lt = miney.Luanti()

.. Important::

    Whenever you see a object "lt" in the documentation, it was created with this line!

If no world is running yet, this line starts one for you — the same as ``miney start`` — and then connects. So
even the shortest script gets you a world; ``miney start`` just lets you open it first and watch what your code
does to it.


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
