=========
Changelog
=========

All notable changes to this project will be documented in this file.
The format is based on `Keep a Changelog <https://keepachangelog.com/en/1.0.0/>`_ (added, changed, deprecated, fixed,
removed and security sections),
and this project adheres to `Semantic Versioning <https://semver.org/spec/v2.0.0.html>`_.

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

