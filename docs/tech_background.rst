.. image:: python-logo.png
   :alt: Python logo
   :align: right

Technical Background
=====================

This page provides an inside view of how Miney works.

Miney's basic idea is, to use `Minetest <https://www.minetest.net/>`_ with `Python <https://www.python.org/>`_.

Minetest's main programming language (besides C++) is `Lua <https://www.lua.org/>`_ and it provides an mighty Lua-API for mod programming.
But Lua isn't the ideal programming language to start programming and mod programming isn't fun,
if you just want to play around with a sandbox.
So we need something like an interface that is accessible by Python.

The interface
------------------------------

For this we've written the `Mineysocket <https://github.com/miney-py/mineysocket>`_ mod as a regular Lua mod.
This mod opens a network port and receives JSON encoded commands.
The most important command is the "lua" command, where it just executes the received Lua code and
sends any return value back.

Miney is using this lua command to execute Lua code inside Minetest.

.. note::

   **And you can use Miney without knowing any Lua or even seeing a single line of Lua code.**

Mineysocket, Windows and the Miney distribution
----------------------------------------------------

Python is the language with batteries included and it ships with a very complete library for nearly everything.
In contrast Lua has the batteries explicitly excluded, so there are nearly no libraries and it misses also a
network library.

So we need a Lua extension for networking, thats `luasocket <https://github.com/diegonehab/luasocket>`_.
And an extension for JSON, thats `lua-cjson <https://luarocks.org/modules/openresty/lua-cjson>`_

Under Linux this should be no big deal, just install these packages (most distributions provide them) and you are ready to go.

Windows
^^^^^^^^^^^^

It isn't that easy for Minetest on Windows. The Minetest binary's where compiled with Visual Studio and the extension
has to be linked against minetest also with the same version of Visual Studio.
So the best way under windows is, to compile Minetest and the Lua extensions by yourself with the same Visual Studio.

And when we already do this, why not replace Lua with `lua-jit <https://luajit.org/>`_ for more speed?

And when we've done all this, why not also bundle a actual python interpreter? And why not preinstall Miney in this
interpreter? Now it would be nice to have a comfortable `launcher <https://github.com/miney-py/launcher>`_.

We've done all this for windows and we call it `Miney Distibution <https://github.com/miney-py/miney_distribution/releases>`_.