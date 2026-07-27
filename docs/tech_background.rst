.. image:: python-logo.png
   :alt: Python logo
   :align: right

Technical Background
=====================

This page provides an inside view of how Miney works.

Miney's basic idea is, to use `Luanti <https://www.luanti.org/>`_ (formerly Minetest) with `Python <https://www.python.org/>`_.

Luanti's main programming language (besides C++) is `Lua <https://www.lua.org/>`_ and it provides a mighty Lua-API for mod programming.
But Lua isn't the ideal programming language to start programming and mod programming isn't fun,
if you just want to play around with a sandbox.
So we need something like an interface that is accessible by Python.

🔌 The interface
------------------------------

To bridge the gap between Python and Lua, Miney relies on a companion mod, the `miney` mod, which must be installed on the Luanti server.
This mod provides the necessary server-side functions to receive Lua code from Miney, execute it, and send back the results.
The most important function is the one that executes arbitrary Lua code.

Miney uses this capability to execute Lua code inside Luanti, effectively giving you control over the game via Python.

.. note::

   **And you can use Miney without knowing any Lua or even seeing a single line of Lua code.**

Miney and the mod pass messages through two files. Nothing joins your game, so there is no account and no
port, and a singleplayer world works as well as a hosted one. The one thing this cannot do is reach a Luanti
on somebody else's computer — a file on your disk is not on their machine.

.. dropdown:: How the file channel works

   The mod keeps two files in Luanti's own ``mod_data`` directory, one per world: ``c2s`` for what Miney
   sends and ``s2c`` for what comes back. Each holds one JSON record per line, and each side only ever
   appends to the file it writes.

   #. **Sending code to the server**: Miney appends one line to ``c2s`` and carries on.

   #. **Execution on the server**: the mod reads that file once per server step, from wherever it stopped
      last time, and runs every complete line it finds inside a sandbox. A line without its final newline
      is not a short record — it is not a record yet, so a request caught half-written is simply read whole
      on the next step. That is what makes a torn read impossible rather than merely unlikely.

   #. **Returning results**: the mod appends the answer to ``s2c`` and flushes once at the end of the step.
      Flushing is not a disk write: it moves the bytes out of the mod's buffer into the operating system,
      which is what lets another program see them.

   #. **Receiving results in Python**: a background thread watches ``s2c`` from its own offset and hands
      each complete line to whichever call is waiting for it.

   Both file handles are opened once when the server starts and kept, because opening a file inside Luanti's
   security sandbox costs a thousand times more than reading from one that is already open. An idle channel
   costs the server a single check per step.

   The one thing this cannot get around is the server step. A mod only ever runs as part of one, so a
   request is picked up on the next step and answered there: about 17 ms in a game you are playing, 30 ms
   on a world ``miney start`` launched. It is also why a paused singleplayer game answers nothing at all —
   with the ESC menu open the server does not step, so no mod code runs either.

   A network client would not pay that. The server spends most of each step waiting for packets
   (``server.cpp:152-158``), and a packet that arrives is handled immediately, mod callback included — so a
   client is answered in the middle of a step rather than at the start of the next one. Measured against the
   same server, before that route was dropped: 1.6 ms over a player account, 31 ms over the files.

   What the files give back is throughput, and that is what a loop actually needs. The mod runs *every*
   complete line it finds in one step, so requests sent without waiting for each answer cost one step
   between them all rather than one step each — measured, 1000 commands within a single server tick.

   Miney uses that by itself. A call with nothing to return does not wait, and the next call that needs an
   answer waits for the lot; a plain ``for`` loop placing 400 nodes one at a time went from 12.2 s to
   0.06 s. Because the mod answers in the order it was asked, an answer arriving is proof that everything
   sent before it is done, so no extra message is needed to synchronise — and an error from a command Miney
   had already moved past is raised at that next call, carrying the line it really came from.

   That trade is why the network route is gone. It bought 30 ms per round trip and cost an account, a
   password, a port, a player standing in the world, a 640 KB ceiling per request, and roughly 1800 lines of
   hand-written UDP, SRP and packet code. Neither the shape of a beginner's script nor a fleet of agents
   driving entities is bounded by that 30 ms — both are bounded by how many answers they ask for.


📦 What you need to get started
----------------------------------------------------

Two pieces have to be in place, and you install exactly one of them:

1. The **Miney Python package**, the client side. This is what you install.
2. The **miney mod**, the server side. It ships inside the Python package, and
   ``uv run miney start`` copies it into every world it creates.

So there is nothing to download by hand, nothing to compile and no external dependency on any operating
system — Miney itself imports only the Python standard library. The :doc:`getting_started/quickstart` walks
through it in four commands.

If you run your own Luanti server rather than letting Miney manage one, you install the mod yourself from
`ContentDB <https://content.luanti.org/packages/Miney/miney/>`_ — see
:doc:`getting_started/installation`.
