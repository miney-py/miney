======
Events
======

An event is something that happened in the world. You say which one you care about, and
Miney runs your function when it happens - see :meth:`lt.callbacks.on()
<miney.callback.Callback.on>` for how to register one, and
:meth:`~miney.callback.Callback.register` for the same thing without a decorator.

Your function is handed one argument: an event object. Which one depends on the event
you subscribed to, and every field it carries is listed below.

.. code-block:: python

    import miney

    with miney.Luanti() as lt:

        @lt.callbacks.on("node_dug")
        def someone_dug(event):
            print(f"{event.player_name} dug {event.node_name} at {event.pos}")

        input("Dig a block in the game. Press Enter to stop.\n")

The events
==========

.. list-table::
   :header-rows: 1
   :widths: 22 30 48

   * - Name
     - Event object
     - When it happens
   * - ``chat_message``
     - :class:`~miney.events.ChatMessageEvent`
     - A player sends a line of chat. Not for ``/commands`` - see below.
   * - ``player_joins``
     - :class:`~miney.events.PlayerJoinsEvent`
     - A player finished logging in and is in the world.
   * - ``player_leaves``
     - :class:`~miney.events.PlayerLeavesEvent`
     - A player leaves, is kicked, or times out.
   * - ``node_dug``
     - :class:`~miney.events.NodeDugEvent`
     - A block was dug away.
   * - ``node_placed``
     - :class:`~miney.events.NodePlacedEvent`
     - A block was placed.
   * - ``node_punched``
     - :class:`~miney.events.NodePunchedEvent`
     - A block was hit, without necessarily being dug.
   * - ``player_dies``
     - :class:`~miney.events.PlayerDiesEvent`
     - A player died.
   * - ``player_respawns``
     - :class:`~miney.events.PlayerRespawnsEvent`
     - A player comes back, before the game moves them.
   * - ``player_punched``
     - :class:`~miney.events.PlayerPunchedEvent`
     - A player was hit by someone or something.
   * - ``player_hp_changed``
     - :class:`~miney.events.PlayerHpChangedEvent`
     - A player lost or gained health.
   * - ``player_near``
     - :class:`~miney.events.PlayerNearEvent`
     - A player comes within a radius of a place you named. Needs ``pos`` and
       ``radius`` — see below.

``player_near`` is the odd one out: it is not something that happens *to* somebody, it
is a place you are watching, so the subscription has to say where and how close:

.. code-block:: python

    from miney import Point

    @lt.callbacks.on("player_near", {"pos": Point(10, 20, 30), "radius": 5})
    def treasure(event):
        lt.chat.send_to_player(event.player_name, "You found it!")

It fires when somebody *arrives*, once — not for every moment they stand there. Walking
out and back in fires it again. ``interval`` sets how many seconds pass between two
looks and is 0.25 unless you say otherwise.

.. important::

   ``radius`` has no default. There is no number that is right for everybody, and one
   that is too large is a handler that goes off for the whole map.

A chat command you registered yourself with :meth:`lt.chat.command()
<miney.Chat.command>` arrives as a :class:`~miney.events.ChatCommandEvent`. It is
not in the table because you do not subscribe to it - registering the command is the
subscription.

Three worked examples
=====================

**A trap door.** Dig one particular block, fall into the dark:

.. code-block:: python

    import miney
    from miney import Point

    with miney.Luanti() as lt:

        @lt.callbacks.on("node_dug", {"node_name": "mcl_core:goldblock"})
        def trapdoor(event):
            lt.nodes.fill(event.pos + Point(0, -1, 0), event.pos + Point(0, -8, 0), "air")
            lt.chat.send_to_player(event.player_name, "Should have left that alone.")

        input("Dig a gold block. Press Enter to stop.\n")

The filter is the interesting part: the comparison happens on the server, so every other
block anybody digs never even reaches your script.

**A safety net.** Send a player home instead of letting them respawn wherever the game
would put them:

.. code-block:: python

    HOME = Point(0, 20, 0)

    @lt.callbacks.on("player_dies")
    def condolences(event):
        lt.chat.send_to_all(f"{event.player_name} died of {event.reason}.")

    @lt.callbacks.on("player_respawns")
    def straight_home(event):
        lt.players[event.player_name].move(destination=HOME)

Two events, because they are two moments: the player is dead at the first one and still
lying where they fell. The game repositions them *after* ``player_respawns``, which is
why the move belongs there and not at death.

**A health bar in the chat**, in three lines:

.. code-block:: python

    @lt.callbacks.on("player_hp_changed")
    def hearts(event):
        full = int(event.hp) // 2
        lt.chat.send_to_player(event.player_name, "♥" * full + "·" * (10 - full))

Filters
=======

A filter is a dictionary of event fields and the values worth waking up for. Every named
field has to match; a list accepts any one of its values:

.. code-block:: python

    @lt.callbacks.on("node_placed", {"node_name": ["mcl_core:lava_source", "mcl_core:tnt"]})
    def no_griefing(event):
        lt.nodes.set(miney.Node(event.pos.x, event.pos.y, event.pos.z, "air"))
        lt.chat.send_to_all(f"Not on my server, {event.player_name}.")

The comparison happens in the mod, before anything is sent, so what a filter rejects
costs no network at all. That is what makes a filter worth setting on the busy events:
``node_dug`` and ``node_placed`` fire for every block every player touches, and an
unfiltered handler on a populated server is a lot of Python for very little.

.. important::

   A filter value is compared with ``==``. It has to be a string, a number, a boolean,
   or a list of those - **a position cannot be filtered on**. ``{"pos": Point(1, 2, 3)}``
   raises a :class:`ValueError` where you typed it, rather than quietly matching nothing.
   Ask for the whole event and decide in your own code:

   .. code-block:: python

       @lt.callbacks.on("node_dug")
       def bedrock_watch(event):
           if event.pos.y < 5:
               lt.chat.send_to_all("Somebody is digging near the bottom of the world.")

Things that will surprise you
=============================

- **A chat command is not a chat message.** Luanti's own handler takes every line
  starting with ``/`` and stops the chain, so ``chat_message`` never sees it. Register
  the command with :meth:`lt.chat.command() <miney.Chat.command>` instead.
- **Blocks a script writes send no block events at all.** Neither
  :meth:`lt.nodes.fill() <miney.Nodes.fill>` nor :meth:`lt.nodes.set()
  <miney.Nodes.set>` sends ``node_placed`` or ``node_dug`` - the first writes through
  the bulk map interface, and the second sets the block directly rather than *placing*
  it the way a player does. These events are about what the people in the world do, and
  a handler that builds cannot set itself off by accident.
- **Not everybody has a name.** A block dug by falling gravel, a player hit by a mob:
  ``player_name`` and ``hitter_name`` are then an empty string, not ``None``.
- **Miney's own player picks itself up.** When the player Miney logged in as dies, Miney
  respawns it - so a ``player_dies`` for that name is followed by a ``player_respawns``
  a moment later without anybody asking for it. Everybody else keeps the death screen
  they are supposed to get.
- **Your handler runs on Miney's callback thread.** A handler that sleeps for ten seconds
  delays every other event by ten seconds. Keep it short.
- **An exception in your handler is logged, not raised.** It cannot take the session down
  with it, so watch your terminal when a handler seems to do nothing.

Reference
=========

.. automodule:: miney.events
   :members:
