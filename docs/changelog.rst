=========
Changelog
=========

All notable changes to this project will be documented in this file.
The format is based on `Keep a Changelog <https://keepachangelog.com/en/1.0.0/>`_ (added, changed, deprecated, fixed,
removed and security sections),
and this project adheres to `Semantic Versioning <https://semver.org/spec/v2.0.0.html>`_.

Unreleased
----------

**Added**

- :attr:`lt.storage <miney.Luanti.storage>`, the world's key-value store, used like a
  dictionary: ``lt.storage["home"] = "10,20,30"`` is still there the next time the script
  runs, and after a server restart. Keys and values are strings, because that is what
  Luanti stores - use :class:`str` and :mod:`json` on the way in.
- ``storage`` in the :meth:`~miney.Lua.run` sandbox, the same store seen from Lua.
- Miney checks that the Lua mod on the server is new enough to talk to, and says so
  before running anything. The two halves ship together, so they only come apart on a
  server where the mod was installed by hand or from ContentDB and only the Python side
  was updated - and the symptom used to be an error inside your own Lua, naming
  something the old mod had never heard of.

**Security**

- The Lua sandbox handed out a way back to the server's real globals, and with them the
  file system. ``getfenv`` was part of the sandbox, and Lua defines ``getfenv(0)`` as
  *the global environment*, so ``getfenv(0).io.open(...)`` read and wrote files on the
  machine running the server, ``getfenv(0).x = 1`` was visible to every other script,
  and the per-connection isolation below was decorative. ``getfenv`` is gone from the
  sandbox. It remains true that the ``miney`` privilege means running code inside the
  server - the privilege now says so, and so does the documentation.

**Changed**

- Miney no longer announces itself in the chat. A script connecting and disconnecting
  used to print ``*** Miney joined the game.`` and ``*** Miney left the game.`` to
  everyone on the server, once per run. Messages from real players are untouched.
- :meth:`~miney.Lua.run` documents that Lua globals survive between calls, belong to
  your connection alone, and that the sandbox has no ``_G``.

**Fixed**

- A variable assigned in :meth:`~miney.Lua.run` no longer leaks into everybody else's
  scripts. All connections shared one sandbox, so a name assigned by one script stayed
  visible to every other script on the server until it restarted - and overwriting a
  name the sandbox provides, ``minetest = nil``, disabled Miney for the whole server.
  Each connection now has its own set of names, cleared when it ends.

- A Lua loop that never ends no longer freezes the server. Lua sent to
  :meth:`~miney.Lua.run` runs inside the server's own step, so ``while true do end``
  stopped the world for everybody until somebody killed the process, losing whatever had
  not been saved. Such a loop is now stopped after about a tenth of a second and comes
  back as an error that says what happened. Scripts that do real work are unaffected -
  the count is of Lua steps, and waiting for the engine is not one.

- :meth:`~miney.Lua.run` says so when the code is too long instead of timing out. The
  server silently drops anything over 640 KB, so a large snippet spent the full timeout
  waiting for an answer that was never coming, then reported only *Timeout*.

- Strings containing control characters no longer fail with a Lua syntax error.
  ``lt.chat.send_to_all("hello\x00world")`` answered *invalid escape sequence* at anyone
  who had never written a line of Lua, because the value was escaped the way JSON does
  it and Lua has no ``\u`` escape. Affected every value on its way into Lua, so also
  node names, player names and chat commands.

v0.6.0
------

The ``miney`` command. Getting from "I have Python" to "a player moves in a 3D world"
no longer means installing and configuring Luanti by hand.

**Added**

- The ``miney`` command line tool, managing a project-local Luanti environment:
  ``init``, ``start``, ``stop``, ``status``, ``logs`` and ``remove``.
- ``miney check`` verifies that Python can drive Luanti and offers to fix what it finds.
- ``miney upgrade`` updates Miney, its Lua mod and Luanti itself.
- ``miney init`` downloads Luanti on Linux as a pkgforge AppImage.
- Games are installed from `ContentDB <https://content.luanti.org>`_.
- Tools, ``Vector``, the privilege list and the connection errors have API documentation for
  the first time.

**Changed**

- Python 3.10 is the minimum version.
- The quickstart is written around ``uv`` and the ``miney`` command, and is now four short
  steps. Everything it used to hide in dropdowns moved to a new *Installation in detail*
  page, and exploring Miney in the Python shell moved to *Basics*.
- The roadmap moved out of the documentation into ``TODO.md``.

**Fixed**

- A normal first login no longer prints a stack trace.
- The API documentation showed a ``lt.players.list()`` method that never existed. Use
  ``lt.players`` directly — it iterates, counts and indexes like a list.
- Around twenty cross-references in the API documentation pointed at nothing and rendered
  as dead text.

v0.5.8
------

Callbacks and events. The is also the first version where we track code changes.

**Added**

- Added ``Callback`` and ``Events``.
- Added chat event and chat command handling with decorators and procedural registration.
- Added tests with pytest.
- A project changelog to the documentation.

**Changed**

- ``invisible`` is the new default for the miney player.

v0.5.0
------

With version 0.5 we removed mineysocket and talking now directly to the server over the Luanti protocol.

