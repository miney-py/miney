.. image:: python-logo.png
   :alt: Python logo
   :align: right

Technical Background
=====================

This page provides an inside view of how Miney works.

Miney's basic idea is, to use `Luanti <https://www.minetest.net/>`_ (formerly Minetest) with `Python <https://www.python.org/>`_.

Luanti's main programming language (besides C++) is `Lua <https://www.lua.org/>`_ and it provides a mighty Lua-API for mod programming.
But Lua isn't the ideal programming language to start programming and mod programming isn't fun,
if you just want to play around with a sandbox.
So we need something like an interface that is accessible by Python.

The interface
------------------------------

Miney implements a native Luanti client in Python. This client connects to the Luanti server just like a regular player would.
This approach allows Miney to interact with the game world directly.

To bridge the gap between Python and Lua, Miney relies on a companion mod, the `miney` mod, which must be installed on the Luanti server.
This mod provides the necessary server-side functions to receive Lua code from the Miney client, execute it, and send back the results.
The most important function is the one that executes arbitrary Lua code.

Miney uses this capability to execute Lua code inside Luanti, effectively giving you control over the game via Python.

.. note::

   **And you can use Miney without knowing any Lua or even seeing a single line of Lua code.**

What you need to get started
----------------------------------------------------

Getting started with Miney is straightforward. You only need two components:

1. The **Miney Python package**: Install it using pip: ``pip install miney``
2. The **Miney mod**: This mod must be installed in your Luanti server's content database.

With this setup, you no longer need to worry about external dependencies or compiling anything yourself, regardless of your operating system.
This simplifies the process significantly compared to the old architecture.
