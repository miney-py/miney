Sound
=====

A world that makes no noise feels like a screenshot. One line of Python fixes that, and
nothing about a sound can be got wrong the way a misplaced block can — it plays, it ends,
and the map is exactly as it was.

Start here
----------

    >>> lt.sound.play("miney_power_up_1")
    <Luanti PlayingSound "sound-1">

Everybody hears it, equally loudly, wherever they are. Give it a place and it behaves
like a real sound instead — quieter the further away you stand:

.. code-block:: python

    lt.sound.play("miney_power_up_1", point=Point(10, 20, 30))

Sounds Miney brings along
-------------------------

``miney_power_up_1`` works on any server, in any game, because Miney's mod ships it. 47
of them come along: lasers, zaps, power-ups, beeps and chimes, all named ``miney_``
something and all listed under :attr:`lt.assets.sounds <miney.Assets.sounds>` like every
other sound the server knows.

.. code-block:: python

    lt.sound.play(lt.assets.sounds.miney.laser_3)
    lt.sound.play(lt.assets.sounds.miney.zap_two_tone)
    lt.sound.play(lt.assets.sounds.miney.three_tone_1)

Nine lasers, twelve power-ups and five of most other things are numbered, so picking one
at random is a line of ordinary Python:

.. code-block:: python

    import random

    lt.sound.play(f"miney_laser_{random.randint(1, 9)}")

.. admonition:: Credit
   :class: seealso

   These are **Digital Audio** by **Kenney Vleugels**, from `kenney.nl
   <https://kenney.nl/assets/digital-audio>`_, released under `CC0
   <http://creativecommons.org/publicdomain/zero/1.0/>`_ — public domain, free to use in
   anything you build. Kenney asks for nothing and gets a thank you anyway.

Finding a name
--------------

Every game brings its own sounds too, and there is no way to guess one of those:
``"mcl_portals_open"`` exists in VoxeLibre and nowhere else.
:attr:`lt.assets.sounds <miney.Assets.sounds>` has every name *this* server knows,
sorted by the mod it came from and discoverable with TAB:

.. code-block:: python

    lt.sound.play(lt.assets.sounds.mcl_portals.open)

.. note::

   A sound name is not a file name. ``default_dig_stone`` is played by that name, while
   the game may hold it as ``default_dig_stone.ogg`` or as a whole set of
   ``default_dig_stone.0.ogg`` to ``.9.ogg`` — one of which is picked at random each
   time, so the same footstep never sounds quite the same twice.

Who hears it, and where it comes from
-------------------------------------

Two parameters sound alike and are not:

* ``player`` — *who hears it*. Only that one person, and nobody standing next to them.
* ``follow`` — *where it comes from*. The sound travels with that player, and everybody
  in earshot hears it move.

.. code-block:: python

    lt.sound.play("miney_zap_1", player=lt.players.Steve)   # in Steve's ears
    lt.sound.play("miney_zap_1", follow=lt.players.Steve)   # from Steve

They combine, so one player can hear a sound that another player carries.

Music
-----

``loop=True`` is what turns a sound into a soundtrack — and it is the one thing here that
keeps going after your script has stopped:

.. code-block:: python

    music = lt.sound.play("miney_low_random", loop=True, gain=0.4)
    # ... the whole show ...
    music.fade_out(3)

A looped ``miney_`` sound makes a hum or a pulse, because they are all short effects. Real
music is a file of your own, and that is the next section.

.. important::

   Somebody has to end a loop: :meth:`~miney.PlayingSound.fade_out`,
   :meth:`~miney.PlayingSound.stop`, or :meth:`lt.sound.stop_all()
   <miney.Sound.stop_all>` for everything at once. Miney's mod stops what your session
   left playing when the session ends, so a forgotten loop does not haunt the world
   forever — but inside a long script it is yours to stop.

   :meth:`~miney.PlayingSound.fade_out` is the kinder one. Cutting music off dead is
   something a player notices.

Your own music
--------------

Any Ogg file on your computer goes into the world the same way a picture does:

.. code-block:: python

    from pathlib import Path

    fanfare = lt.assets.upload(Path("fanfare.ogg"))
    lt.sound.play(fanfare)

:meth:`lt.assets.upload() <miney.Assets.upload>` hands back ``miney_3f9a1c7b2e04.ogg``
and :meth:`~miney.Sound.play` drops the ``.ogg`` for you, so the name goes straight from
one to the other. It also waits until the file has really reached the players, so the
next line can use it.

A moment worth hearing
----------------------

Everything together:

.. code-block:: python

    import miney
    import time

    lt = miney.Luanti()
    point = lt.players[0].position

    music = lt.sound.play(lt.assets.sounds.miney.low_random, loop=True, gain=0.3)

    for i in range(5):
        lt.sound.play("miney_power_up_1", point=point, pitch=1 + i / 4, distance=16)
        lt.particles.spawn(point + miney.Point(0, 2, 0), color="#ffcc00", amount=200)
        time.sleep(0.5)

    music.fade_out(2)

.. autoclass:: miney.Sound
   :members:

.. autoclass:: miney.PlayingSound
   :members:
