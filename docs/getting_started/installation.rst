Installation in detail
======================

The :doc:`quickstart` gets you a running world in four commands and explains nothing it
does not have to. This page is the other half: what those commands actually do, and the
cases the quickstart walks past.

Read it when something does not work, when you want a different setup, or simply when
you want to know what happened on your machine.

Miney ships in two places: the Python library on `PyPI <https://pypi.org/project/miney/>`_, and the Lua mod
on `Luanti ContentDB <https://content.luanti.org/packages/Miney/miney/>`_. Installing the library is enough —
it carries the mod with it.

.. contents:: On this page
   :local:
   :depth: 1


🧰 What is uv, and why do we use it?
-------------------------------------

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


📁 What is that ``.venv`` folder?
----------------------------------

A *virtual environment*: a private Python installation belonging to this one project. Libraries you install
here cannot break another project, and another project cannot break this one.

You never have to activate or even open it — ``uv run`` finds it on its own. If you delete the
folder, ``uv venv`` and ``uv pip install miney`` recreate it.


.. _already-have-python:

🐍 Already have Python? Install with pip instead
-------------------------------------------------

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


🪟 On Windows, ``python`` may open the Microsoft Store
-------------------------------------------------------

Windows ships a placeholder named ``python.exe``. If you have never installed Python from python.org, typing
``python`` opens the Microsoft Store instead of starting Python — even though ``uv`` just downloaded a perfectly
good Python for you.

That Python lives in your user folder and is deliberately kept out of your search path, so that it cannot
interfere with anything else on your system. ``uv run`` addresses it directly. This is why every command in
this documentation starts with ``uv run``.


🗂️ Where Miney puts things
----------------------------

``uv run miney start`` sets up two things, in two places:

* **Luanti itself and its games** go into a plain ``Luanti`` folder in your home directory. It is an ordinary
  Luanti install you could even start on its own, and every Miney project on this machine shares it — so it is
  downloaded only once, no matter how many projects you make.
* **Your world, its settings and the Miney mod** go into the ``.miney`` folder next to your code. Delete the
  project folder and that world is gone; the shared Luanti in your home directory stays for your other projects.

The server listens on ``127.0.0.1`` (this machine only), so nobody else on your network can reach your world
and Windows does not raise a firewall prompt for it.


⌨️ The ``miney`` commands
---------------------------

Every command starts with ``uv run`` so it uses the Python in your ``.venv``:

* ``uv run miney start`` — start the server and open your world.
* ``uv run miney stop`` — stop the server and close the window.
* ``uv run miney status`` — what is installed and what is running.
* ``uv run miney check`` — verify that Python can drive Luanti.
* ``uv run miney logs -f`` — watch the server log live.
* ``uv run miney upgrade`` — get the newest Miney.
* ``uv run miney remove`` — delete a world or the whole environment.
* ``uv run miney start --help`` — all options of a command.


🩺 Checking your setup
-----------------------

With a world open, confirm that Python and Luanti really talk to each other:

.. code-block:: text

   uv run miney check

.. code-block:: text

   ✅ Miney       0.7.0 on Python 3.12.3
   ✅ Luanti      5.16.1 (bundled)
   ✅ World       'minetest_game' (Minetest Game)
   ✅ Miney mod   installed and up to date
   ✅ Server      running on port 30000
   ✅ Connection  talking to Luanti 5.16.1
   ✅ Content     412 node types, 34 tool types

   Everything is ready. Your Python scripts can drive this world.

Each line is one layer the one above it stands on, so a failure tells you *where* the problem is rather than
only that there is one. When Miney can fix it, it explains the problem, shows you the command that fixes it,
and asks before doing anything:

.. code-block:: text

   ✅ Miney       0.6.0 on Python 3.12.3
   ✅ Luanti      5.16.1 (bundled)
   ✅ World       'minetest_game' (Minetest Game)
   ✅ Miney mod   installed and up to date
   ❌ Server      not running

   I can start the server for you. That is the same as running:
     uv run miney start --no-client
   Shall I start the server? [Y/n]:

Answer ``n`` and it prints the command instead, so you can run it yourself. ``miney check`` never downloads,
creates or starts anything without a yes.


🔄 Keeping Miney up to date
----------------------------

``uv run miney status`` tells you which Miney you have, and says so when a newer one has been released:

.. code-block:: text

   Miney: 0.6.0
     A newer Miney is available: 0.7.0. Get it with: uv run miney upgrade

``uv run miney upgrade`` asks two separate questions — first whether to update Luanti, then whether to update
Miney. Nothing is installed until you say yes, and saying no to one says nothing about the other. There are
good reasons to stay on a Luanti that works.

Your worlds are never part of a Luanti update: they live in the ``.miney`` folder of your project, not in the
Luanti installation. The games, mods and settings inside that installation are carried over to the new
version. A Luanti that came from your package manager or from Flatpak is left alone entirely — Miney only
replaces the one it downloaded itself, and tells you the command for the other case.

If a world is still running, the Luanti update is refused until you ``uv run miney stop``. Replacing a
running program is how installations break.

In the rare environment where Miney cannot upgrade itself, it prints the command with the reason, and running
that line yourself works.

The mod inside your worlds needs no separate step. It travels inside the Miney package, and the next
``uv run miney start`` puts the new one into every world by itself. If a world's server is still running,
stop it first — a running world is left untouched on purpose.


🎮 Choosing a different game
-----------------------------

``miney start`` uses `Minetest Game <https://content.luanti.org/packages/Minetest/minetest_game/>`_, and so
does every example in this documentation. VoxeLibre (``mineclone2``) is downloaded alongside it, so switching to
it is instant — no second download:

.. code-block:: text

   uv run miney start --game mineclone2

.. warning::

   VoxeLibre (``mineclone2``) uses **different node names** than Minetest Game — ``mcl_core:dirt`` instead of
   ``default:dirt``, and so on. The documentation examples assume Minetest Game, so start there while you are
   learning and explore other games once you know your way around.


🐧 Where Miney gets Luanti from on Linux
-----------------------------------------

Nothing to do — ``uv run miney init`` downloads Luanti on Linux just like on Windows and macOS, and no
command needs ``sudo``. Luanti itself publishes no Linux build, so Miney takes the
`AppImage <https://github.com/pkgforge-dev/Luanti-AppImage>`_ instead, unpacks it once into a plain
``Luanti`` folder in your home directory and runs it from there like any other program.

Already have Luanti installed, from your package manager or from Flatpak? Miney uses that one and downloads
nothing, as long as it is version 5.9 or newer.

The one exception is an unusual processor — anything that is not a 64-bit Intel, AMD or ARM chip. There is
no download for those, and Miney will print the command that installs Luanti on your system, for example:

.. code-block:: text

   sudo apt install luanti      # Debian/Ubuntu
   flatpak install flathub org.luanti.luanti

Install Luanti that way, then run ``uv run miney start`` again.


🖥️ I already run my own Luanti server
---------------------------------------

You do not have to let Miney manage Luanti. If you run a server yourself, install the Miney mod in it and
Miney connects to it instead:

* Start Luanti, click **Content**, then **Browse online content**, search for **miney** and install it.
* Create a world and enable the **miney** mod under **Select Mods**. Then just **Play Game** — you do not
  need **Host Server**.
* Run your script. ``miney.Luanti()`` finds that world by itself, whether you are playing it on your own or
  hosting it for others.

.. important::

   Miney reaches a world on your own computer through Luanti's own files, so it never joins your game.
   That is why singleplayer works, and why nobody shows up in your player list.

If two worlds are running at once, Miney cannot tell which one you mean and says so, listing them. Name the
one you want:

.. code-block:: python

   lt = miney.Luanti(world="myworld")

Pass ``autostart=False`` if Miney should never start a server of its own.

.. note::

   A Luanti on **another** computer is out of reach. Miney talks to the mod through two files in Luanti's
   own directory, so the server has to be one this machine can see on disk. Run your script on the machine
   the server is on.


⚡ One command from nothing at all
-----------------------------------

If you are comfortable running an install script, this single line does everything the quickstart does —
installs ``uv``, creates the project, installs Miney and starts a world — in one go. Paste it into a
**new, empty folder**.

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
The step-by-step route in the :doc:`quickstart` is the same thing, one command at a time, and stays the
recommended way in.
