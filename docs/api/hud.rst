Hud
===

A chat message scrolls away. ``player.hud`` is the half that stays: text, markers,
pictures and bars that sit on top of the world until something takes them down.

Everything here belongs to one player, because that is how Luanti works - there is no
screen the whole server shares. Showing something to everybody is a loop, and a good
one to write:

.. code-block:: python

    for player in lt.players:
        player.hud.text("The dragon woke up!")

Start here
----------

    >>> p = lt.players.Steve
    >>> p.hud.text("Welcome!")
    <HudElement "text_1" (text) for "Steve">

That is the whole first step: one line, one argument, something on the screen. What
comes back is a handle, and it is how the text changes later:

.. code-block:: python

    score = p.hud.text("Score: 0", position="top left", name="score")

    for point in range(1, 11):
        score.text = f"Score: {point}"

Reading a field gives back what you last set. Luanti has no way to read a HUD element
back, so Miney answers from memory rather than pretending otherwise.

The nine places
---------------

``position`` takes one of nine names - ``"top left"``, ``"top"``, ``"top right"``,
``"left"``, ``"center"``, ``"right"``, ``"bottom left"``, ``"bottom"``,
``"bottom right"`` - or a ``(x, y)`` pair between 0 and 1 for anywhere else. The
default is the middle of the screen.

Luanti draws an element *from* its position outwards, which puts anything in a corner
half off the screen. Miney sets the alignment that points it back inwards, so
``"bottom right"`` really is the bottom right corner.

More than text
--------------

.. code-block:: python

    # a marker in the world, visible through walls, with its distance
    p.hud.waypoint(Point(10, 20, 30), "Base", color="#00ff00")

    # a picture the game ships, four times its own size
    p.hud.image(lt.assets.textures.default.mese_crystal, scale=4)

    # a picture of your own - anything that is not a str is uploaded first
    p.hud.image(Path("cat.png"), position="top right")
    p.hud.image(figure, scale=(-50, -50))          # half the screen

    # a row of half-pictures, the way the health bar is drawn
    hearts = p.hud.statbar("heart.png", value=10, max_value=20)

Every one of those is a line around :meth:`~miney.Hud.add`, which is where the whole
field list lives. Its docstring shows the equivalent call for each.

.. important::

   A texture name that does not exist draws **nothing at all** - no error, no warning,
   just an empty spot. That is the one thing worth checking first when something does
   not show up. :attr:`lt.assets.textures <miney.Assets.textures>` is there so the
   names can be found with TAB instead of typed from memory.

What Luanti draws by itself
---------------------------

The hearts, the crosshair, the hotbar and the rest are not elements, they are
properties:

.. code-block:: python

    p.hud.healthbar = False
    p.hud.crosshair = False
    p.hud.hotbar_slots = 4

Traps
-----

.. warning::

   An element stays on the screen long after the script that made it has ended. Only
   :meth:`~miney.HudElement.remove` or :meth:`~miney.Hud.clear` takes it down.

   Giving an element a ``name`` replaces the one that had it; leaving the name out adds
   another. Run a nameless script twice and there are two texts sitting on top of each
   other.

   Nothing survives the player leaving the game. They come back to an empty screen, and
   a handle from before then raises :class:`~miney.exceptions.HudElementGone` the next
   time you write to it.

.. autoclass:: miney.Hud
   :members:

.. autoclass:: miney.HudElement
   :members:

.. autodata:: miney.hud.POSITIONS
