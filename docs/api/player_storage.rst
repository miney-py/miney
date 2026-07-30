Player storage
==============

``player.storage`` is :doc:`lt.storage <storage>` for one person. Everything a script
knows is gone when it ends, and this is the exception: what you write here stays with
that player after they log out, and after the server was restarted.

It is a dictionary, so there is nothing new to learn - ``in``, ``len()``, ``for``,
``.get()``, ``.pop()``, ``.update()`` and ``del`` all behave the way you expect.

:Example:

    >>> player = lt.players.Steve
    >>> player.storage["home"] = "10,20,30"
    >>> player.storage["home"]
    '10,20,30'
    >>> "home" in player.storage
    True

The first time somebody plays there is nothing stored for them yet, so read with
``.get(key, default)`` and that case handles itself:

.. code-block:: python

    visits = int(player.storage.get("visits", "0")) + 1
    player.storage["visits"] = str(visits)
    lt.chat.send_to_player(player.name, f"Welcome back! Visit number {visits}.")

Keys and values are always strings, because that is all Luanti stores. Use :class:`str`
for single values and :mod:`json` for lists and dictionaries.

Which one do you want?

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Store
     - What belongs in it
   * - :doc:`lt.storage <storage>`
     - One per world. Where the castle is, how many blocks the class placed together,
       the high score.
   * - ``player.storage``
     - One per player. Where *they* set their home, how far *they* got, what *they*
       answered last time.

.. note::

   Luanti keeps this in the same place a game keeps its own notes about a player, next
   to things like which game mode they are in. Miney puts your keys in a corner of their
   own, so yours are the only ones you see and the only ones ``clear()`` removes, and
   nothing you write can confuse the game about that player.

.. autoclass:: miney.PlayerStorage
   :members:
   :inherited-members: MutableMapping, Mapping, Collection, Iterable, Container, Sized
   :special-members: __getitem__, __setitem__, __delitem__, __iter__, __len__
