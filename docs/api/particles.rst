Particles
=========

A particle is a small image that flies through the world for a second and is gone.
Nothing is built and nothing is dug, so there is no way to get it wrong — which makes
``lt.particles`` the cheapest way to make something look like it happened.

Start here
----------

    >>> lt.particles.spawn(Point(10, 20, 30))
    <Luanti ParticleSpawner "spawner-1">

One line, and a puff of white sparks goes up where you pointed. Give it a colour and
there are more of them:

.. code-block:: python

    lt.particles.spawn(Point(10, 20, 30), color="#ffcc00", amount=300)

Two clocks
----------

``time`` and ``life`` sound alike and are not:

* ``time`` — how long *new* particles keep coming.
* ``life`` — how long *each one* lasts once it is out.

A firework is a short ``time`` and a long ``life``: everything leaves at once and then
hangs in the air. A campfire is the other way round.

.. important::

   ``time=0`` does not mean "no time". It means the spawner never stops on its own, and
   somebody has to stop it:

   .. code-block:: python

       smoke = lt.particles.spawn(Point(10, 20, 30), color="#888888", time=0)
       smoke.stop()

   Miney's mod deletes what your session left behind when the session ends, so a
   forgotten spawner does not haunt the world forever. Inside a long script it is still
   yours to stop — :meth:`~miney.ParticleSpawner.stop`, or
   :meth:`lt.particles.stop_all() <miney.Particles.stop_all>` for all of them at once.

The picture
-----------

Miney ships the image the particles are made of, so ``spawn()`` looks the same in
VoxeLibre, in Minetest Game and in whatever else somebody plays. ``color`` tints it.

.. warning::

   A texture name is never checked by the server. Give ``texture=`` a name the game
   does not have and nothing goes wrong here: the *client* prints two red lines into a
   log nobody is reading, and the sparks come out as plain white squares.

   :attr:`lt.assets.textures <miney.Luanti.assets>` is the way to a name that exists,
   discoverable with TAB:

   .. code-block:: python

       lt.particles.spawn(point, texture=lt.assets.textures.default.dirt)

A firework
----------

Everything together, and the thing worth typing first:

.. code-block:: python

    import miney
    import time

    lt = miney.Luanti()
    point = lt.players[0].position + miney.Point(0, 15, 0)

    for color in ["#ff6666", "#66ccff", "#ffcc00"]:
        lt.particles.spawn(
            point, color=color, amount=400,
            time=0.2,      # everything leaves in a fifth of a second
            life=2,        # and then falls for two
            speed=7, spread=0.5, gravity=4, size=2,
        )
        time.sleep(1.5)

.. autoclass:: miney.Particles
   :members:

.. autoclass:: miney.ParticleSpawner
   :members:
