Storage
=======

A script forgets everything when it ends. Python variables are gone with the process,
and the Lua names from :meth:`~miney.Lua.run` are gone with the connection. ``lt.storage``
is the exception: what you write here is stored in the world and is still there the next
time you run your script, and after the server was restarted.

It is a dictionary, so there is nothing new to learn - ``in``, ``len()``, ``for``,
``.get()``, ``.pop()``, ``.update()`` and ``del`` behave the way you expect.

:Example:

    >>> lt.storage["home"] = "10,20,30"
    >>> lt.storage["home"]
    '10,20,30'
    >>> "home" in lt.storage
    True
    >>> del lt.storage["home"]

Keys and values are always strings, because that is all Luanti stores. Miney does not
hide that: a number raises a :class:`TypeError` rather than coming back as text you did
not write. Use :class:`str` for single values and :mod:`json` for lists and dictionaries.

.. important::

   There is one store per world, shared by every Miney script connected to it - it is a
   noticeboard, not a private drawer. Give your keys a prefix if more than one project
   uses the same world.

   The keys belong to Miney alone: Luanti files them under the mod that wrote them, so
   no other mod on the server sees them, and you never collide with one. That is a
   namespace and not a secret - the store is a plain file in the world directory.

.. autoclass:: miney.Storage
   :members:
   :special-members: __getitem__, __setitem__, __delitem__, __iter__, __len__
