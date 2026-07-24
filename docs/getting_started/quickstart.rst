Quickstart
==========

Four commands, and your Python is changing a 3D world.

You need two things: **Luanti**, the game Miney drives, and the **Python library** you write your code
against. You install the library, and Miney brings Luanti along — you do not download or set up the game
yourself.

.. tip::

   Every step here is the short version. :doc:`installation` explains what each command does and covers the
   cases this page walks past — an existing Python, a different game, your own server.


🧰 Step 1: Install uv
---------------------

``uv`` is the tool we use to install Python and Miney. It is a single small program and needs no
administrator rights.

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

Already have Python and know your way around it? Then use
:ref:`pip instead <already-have-python>` and skip to step 3.


📁 Step 2: Create a folder for your code
----------------------------------------

In your new terminal window:

.. code-block:: text

   mkdir miney-world
   cd miney-world
   uv venv
   uv pip install miney

``uv venv`` creates a folder named ``.venv`` next to your code. That is where Miney gets installed, so it stays
separate from everything else on your computer. If you have no Python yet, ``uv`` downloads a current version at
this point — this takes a moment and only happens once.


🌍 Step 3: Start Luanti
-----------------------

One command downloads Luanti, installs the Miney mod, creates a world and opens it on your screen:

.. code-block:: text

   uv run miney start

The very first time, it asks which game your world should use. Press **1** (or just Enter) for
**Minetest Game** — the calm building sandbox every example in these docs is written for. You only answer
this once.

Then it downloads, sets up and opens your world, telling you about each step:

.. code-block:: text

   No Luanti found. Downloading v5.16.1 into ~/Luanti...
   Luanti 5.16.1 is ready.
   Downloading Minetest Game from ContentDB...
   Environment ready in .miney.
   Started Luanti server for 'minetest_game' on port 30000.
   Opened your client as 'miney'.
   Your world is open. The server keeps running in the background, so closing the game window does not stop it.
   Stop it when you are done: uv run miney stop

Later runs skip the downloads and open the world straight away.

.. important::

   The **server keeps running in the background** even after you close the game window — that is what lets your
   Python scripts connect to it. When you are done, stop it with ``uv run miney stop``.

Leave this world running. In the next step you write Python that connects to it and watches your changes
appear.


▶️ Step 4: Run your code with ``uv run``
----------------------------------------

Save your Python file in the ``miney-world`` folder and start it like this:

.. code-block:: text

   uv run world.py

.. warning::

   Start your scripts with ``uv run world.py``, **not** with ``python world.py``.

   Only ``uv run`` knows about the ``.venv`` folder from step 2. Plain ``python`` either does not exist yet or is
   a different Python that has never heard of Miney, and you get ``ModuleNotFoundError: No module named 'miney'``.


🐍 First lines of code
----------------------

Save this as ``world.py`` in your ``miney-world`` folder:

.. code-block:: python

    import miney

    lt = miney.Luanti()

    lt.chat.send_to_all("Hello from Python!")
    lt.time_of_day = 0.5

Run it with ``uv run world.py``, then look at your Luanti window: your message is in the chat, and the sun
jumped to midday. Those are the first three lines you will write in every Miney program — import Miney,
connect, then tell the world what to do.

.. important::

    Whenever you see the object ``lt`` in this documentation, it was created with ``lt = miney.Luanti()``.
    Examples leave those lines out to stay short; your own file always needs them at the top.

If no world is running yet, ``miney.Luanti()`` starts one for you — the same as ``miney start`` — and then
connects. So even the shortest script gets you a world; ``miney start`` just lets you open it first and watch
what your code does to it.


🗺️ Where to go next
-------------------

.. grid:: 1 1 3 3
   :gutter: 3

   .. grid-item-card:: :octicon:`mortar-board;1.5em;sd-text-info` Basics
      :link: basics
      :link-type: doc

      Coordinates, nodes, and the ``lt`` object explained properly.

   .. grid-item-card:: :octicon:`beaker;1.5em;sd-text-info` Examples
      :link: ../examples
      :link-type: doc

      Working scripts to copy, run and take apart.

   .. grid-item-card:: :octicon:`tools;1.5em;sd-text-info` Installation in detail
      :link: installation
      :link-type: doc

      What every command did, and what to do when something breaks.


🔧 Something not working?
-------------------------

.. code-block:: text

   uv run miney check

It walks every layer between your Python and the running world, tells you which one broke, and offers to fix
it. See :doc:`installation` for what it checks and what else the ``miney`` command can do.
