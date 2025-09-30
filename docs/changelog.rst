=========
Changelog
=========

All notable changes to this project will be documented in this file.
The format is based on `Keep a Changelog <https://keepachangelog.com/en/1.0.0/>`_ (added, changed, deprecated, fixed,
removed and security sections),
and this project adheres to `Semantic Versioning <https://semver.org/spec/v2.0.0.html>`_.

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

