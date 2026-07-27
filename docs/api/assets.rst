Assets
======

Two things live here, and they are both about pictures.

**The pictures the game already has.** Every texture in Luanti is a file name like
``default_dirt.png``, and nothing tells you which ones exist - a name that does not
exist simply draws nothing at all. So ``lt.assets.textures`` makes them findable with
TAB, grouped by the mod they came from:

    >>> lt.assets.textures.default.dirt
    'default_dirt.png'
    >>> lt.assets.textures.mcl_core.stone
    'mcl_core_stone.png'

**The pictures you make yourself.** Anything Python can draw goes into the world.
:meth:`~miney.Assets.upload` takes a file, raw bytes, a Pillow image or a matplotlib
figure and gives back a name you can use anywhere a texture name goes:

.. code-block:: python

    from pathlib import Path

    name = lt.assets.upload(Path("cat.png"))
    lt.players.Steve.hud.image(name)

Neither Pillow nor matplotlib is needed to install Miney. They are recognised by the
methods they carry, so if you have them, they work, and if you do not, nothing here
changes.

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

   **The name is a hash of the picture.** Uploading the same one twice is free, and a
   *changed* picture gets a *different* name. That is not a quirk of Miney: Luanti
   refuses to know one name twice, so a chart that updates cannot keep its old name.
   Whatever shows the picture has to be told the new one.

.. warning::

   The picture travels over the same connection as the game, so a big one is felt as a
   stutter by whoever receives it. A 800x600 chart is 40-80 KB and nobody notices it;
   anything above :data:`~miney.assets.MAX_UPLOAD` is refused.

Luanti calls all of this **media**. Said once here so that the Luanti documentation and
the forums are searchable from what you have read.

.. autoclass:: miney.Assets
   :members:

.. autodata:: miney.assets.MAX_UPLOAD

.. autodata:: miney.assets.POLL_INTERVAL
