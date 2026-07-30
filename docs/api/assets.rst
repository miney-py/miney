Assets
======

Two things live here: what the game brought with it, and what you bring yourself.

**What the game already has.** Every texture in Luanti is a file name like
``default_dirt.png`` and every sound is a name like ``default_dig_stone``, and nothing
tells you which ones exist - one that does not simply draws nothing and plays nothing. So
they are here to be found with TAB, grouped by the mod they came from:

    >>> lt.assets.textures.default.dirt
    'default_dirt.png'
    >>> lt.assets.sounds.default.dig_stone
    'default_dig_stone'

.. note::

   A sound name is not a file name. ``default_dig_stone`` may be one
   ``default_dig_stone.ogg`` on disk or a whole set of ``default_dig_stone.0.ogg`` to
   ``.9.ogg``, one of which the game picks at random. Miney lists the name you play, not
   the files behind it.

**What you make yourself.** Anything Python can draw, and any Ogg file you have.
:meth:`~miney.Assets.upload` takes a file, raw bytes, a Pillow image or a matplotlib
figure and gives back a name you can use anywhere a texture or sound name goes:

.. code-block:: python

    from pathlib import Path

    name = lt.assets.upload(Path("cat.png"))
    lt.players.Steve.hud.image(name)

    lt.sound.play(lt.assets.upload(Path("fanfare.ogg")))

Neither Pillow nor matplotlib is needed to install Miney. They are recognised by the
methods they carry, so if you have them, they work, and if you do not, nothing here
changes.

.. important::

   An uploaded sound comes back as ``miney_3f9a1c7b2e04.ogg`` and is *played* as
   ``miney_3f9a1c7b2e04``. :meth:`lt.sound.play() <miney.Sound.play>` drops the extension
   for you, so the name goes straight from one call to the other.

Who sees it, and for how long
-----------------------------

Three levels, and two optional arguments to say which one you want:

.. code-block:: python

    lt.assets.upload(chart, player=lt.players.Steve)   # only Steve, then forgotten
    lt.assets.upload(chart)                            # everybody, until the server stops
    lt.assets.upload(logo, keep=True)                  # everybody, across restarts

The first is the one for a picture that *changes* - a chart redrawn every few seconds -
because it is the only one that does not pile up. The middle one is the default,
because it is what "show this picture" means without thinking any further.

.. important::

   **The name is a hash of the file.** Uploading the same one twice is free, and a
   *changed* picture gets a *different* name. That is not a quirk of Miney: Luanti
   refuses to know one name twice, so a chart that updates cannot keep its old name.
   Whatever shows the picture has to be told the new one.

.. warning::

   It travels over the same connection as the game, so a big one is felt as a stutter by
   whoever receives it. A 800x600 chart is 40-80 KB and nobody notices it; a minute of
   Ogg is closer to a megabyte, so upload music before the show rather than during it.
   Anything above :data:`~miney.assets.MAX_UPLOAD` is refused.

Luanti calls all of this **media**. Said once here so that the Luanti documentation and
the forums are searchable from what you have read.

.. seealso::

   :doc:`sound` — what to do with a sound name once you have one.

.. autoclass:: miney.Assets
   :members:

.. autodata:: miney.assets.MAX_UPLOAD

.. autodata:: miney.assets.POLL_INTERVAL
