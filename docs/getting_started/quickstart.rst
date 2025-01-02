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

Linux
^^^^^

 * Download the latest Luanti by following instruction on https://www.luanti.org/downloads/
 * You should have Python 3 installed, if not, install it with your package manager.

MacOS
^^^^^

Untested

For all Plattforms
^^^^^^^^^^^^^^^^^^

 * **Luanti**:
    * Install the Miney mod by starting Luanti and clicking to "Content", "Browse online content" and searching for miney.
 * **Python**:
    * You can install Miney systemwide by typing this in a command prompt: "pip install miney"
    * Suggestion: Make yourself familiar with venv's, so you can isolate different development environments.
      A good starting point is https://docs.python.org/3/tutorial/venv.html

First lines of code
-------------------

The first lines of code with Miney should be the import statement and the creation of the Miney object "mt". This will
connect Miney to your already running Luanti.

::

    import miney

    lt = miney.Luanti()

.. Important::

    Whenever you see a object "lt" in the documentation, it was created with this line!