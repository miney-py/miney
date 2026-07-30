"""
Sparks, smoke and fireworks: the little images the engine throws around for you.
"""
from itertools import count
from typing import TYPE_CHECKING, Any, Optional, Union

# The same colours as on the screen, so "#ffcc00" means one thing in this library.
from .hud import _color

if TYPE_CHECKING:
    from .luanti import Luanti
    from .player import Player
    from .point import Point

#: The image a particle is made of unless something says otherwise.
#:
#: It ships with Miney's own mod (``mod_data/miney/textures/``), which is the whole
#: point: a texture name is never checked by the server, so a name a game does not have
#: costs two red lines in the *client's* console - a place nobody running a Python script
#: is looking - and comes out as plain white squares. This one is there in every game.
SPARK = "miney_spark.png"

#: What every named parameter of :meth:`Particles.spawn` is called once it reaches Luanti,
#: so that ``extra`` can say which parameter to use instead of a field it collides with.
_OWNED = {
    "pos": "point", "radius": "spread", "vel": "speed", "acc": "gravity",
    "exptime": "life", "playername": "player", "amount": "amount", "time": "time",
    "size": "size", "glow": "glow", "texture": "texture",
}


def _number(value: Any, name: str, minimum: float = 0.0) -> float:
    """
    :param value: What the parameter was given.
    :param name: Its name, for the error message.
    :param minimum: The smallest value that makes sense.
    :return: The value as a float.
    :raises TypeError: If it is not a number.
    :raises ValueError: If it is below the minimum.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} is a number, not {value!r}.")
    if value < minimum:
        raise ValueError(f"{name} cannot be less than {minimum}, and was {value!r}.")
    return float(value)


def _vector(value: Any) -> dict:
    """
    :param value: A :class:`~miney.Point`, or anything else with ``x``, ``y`` and ``z``.
    :return: ``{"x": ..., "y": ..., "z": ...}``, which is what Luanti reads.
    :raises TypeError: For anything without the three of them.
    """
    try:
        return {"x": float(value.x), "y": float(value.y), "z": float(value.z)}
    except (AttributeError, TypeError, ValueError):
        raise TypeError(
            f"{value!r} is not a place in the world. Use a Point, as in "
            f"Point(10, 20, 30)."
        ) from None


def _texture(texture: Optional[str], color: Optional[Union[str, int]]) -> str:
    """
    Build the texture string, tint and all.

    :param texture: A texture name, or ``None`` for Miney's own spark.
    :param color: ``"#rrggbb"``, an integer, or ``None`` to leave the image as it is.
    :return: What goes into the spawner's ``texture`` field.
    :raises TypeError: If the texture is not a name.
    :raises ValueError: If the colour is not one, or carries an alpha value.
    """
    if texture is None:
        texture = SPARK
    elif not isinstance(texture, str):
        raise TypeError(
            f"texture is the name of an image, as in \"{SPARK}\", not {texture!r}."
        )
    if color is None:
        return texture
    number = _color(color)
    if number > 0xFFFFFF:
        # Luanti's own words on "[colorize": the colour "should not use alpha", and
        # anything else "leads to undefined behavior".
        raise ValueError(
            f"A particle colour has no transparency. Write it as \"#rrggbb\", for "
            f"example \"#ffcc00\" for gold, and use glow to make it brighter."
        )
    return f"{texture}^[colorize:#{number:06x}:255"


class ParticleSpawner:
    """
    A running particle spawner, and the way to end it.

    You never make one of these - :meth:`Particles.spawn` hands it back::

        >>> fire = lt.particles.spawn(Point(10, 20, 30), color="#ff6600", time=0)
        >>> fire.stop()

    It is also a context manager, which is the tidier way to say the same thing::

        >>> with lt.particles.spawn(Point(10, 20, 30), time=0) as smoke:
        ...     build_the_thing()
        ...                                 # stopped on the way out, come what may
    """

    def __init__(self, particles: "Particles", key: str):
        """
        :param particles: The :class:`Particles` this one came from.
        :param key: How the server knows this spawner.
        """
        self._particles = particles
        #: How the server knows this spawner.
        self.key = key

    def __repr__(self) -> str:
        return f'<Luanti ParticleSpawner "{self.key}">'

    def __enter__(self) -> "ParticleSpawner":
        return self

    def __exit__(self, *_) -> None:
        self.stop()

    def stop(self) -> None:
        """
        End this spawner. Particles already in the air live out their time.

        Stopping one twice is not an error, and neither is stopping one that ran out on
        its own - only a spawner made with ``time=0`` really needs this.

        .. code-block:: python

            fire = lt.particles.spawn(Point(10, 20, 30), color="#ff6600", time=0)
            # ... a while later ...
            fire.stop()
        """
        self._particles._delete(self.key)


class Particles:
    """
    Sparks, smoke and fireworks.

    Reached through :attr:`lt.particles <miney.Luanti.particles>` and never created
    directly::

        >>> lt.particles.spawn(Point(10, 20, 30))
        <Luanti ParticleSpawner "spawner-1">

    A particle is a small image that flies through the world and disappears. Nothing
    about it is part of the map: nothing is built, nothing is dug, and a player cannot
    touch it. It is there to be looked at, which makes it the cheapest way to make
    something feel like it happened.

    .. important::

        Particles keep going after your script has ended. One made with ``time=0`` runs
        until somebody stops it - :meth:`ParticleSpawner.stop`, :meth:`stop_all`, or
        your session ending, because Miney's mod clears out what a connection left
        behind.
    """

    def __init__(self, luanti: "Luanti"):
        """
        :param luanti: The parent :class:`~miney.Luanti` object.
        """
        self.lt = luanti
        self._keys = count(1)

    def __repr__(self) -> str:
        return "<Luanti Particles>"

    def _delete(self, key: Optional[str]) -> None:
        """
        :param key: The spawner to end, or ``None`` for every one of them.
        """
        if key is None:
            self.lt.lua.run(
                "if miney_spawners then "
                "for _, id in pairs(miney_spawners) do "
                "minetest.delete_particlespawner(id) end miney_spawners = {} end",
                wait=False,
            )
            return
        name = self.lt.lua.dumps(key)
        self.lt.lua.run(
            f"if miney_spawners and miney_spawners[{name}] then "
            f"minetest.delete_particlespawner(miney_spawners[{name}]) "
            f"miney_spawners[{name}] = nil end",
            wait=False,
        )

    def spawn(
        self,
        point: "Point",
        *,
        color: Optional[Union[str, int]] = None,
        amount: int = 100,
        time: float = 1.0,
        life: float = 1.0,
        size: float = 1.0,
        speed: float = 0.0,
        spread: float = 0.0,
        gravity: float = 0.0,
        glow: int = 14,
        texture: Optional[str] = None,
        player: Optional[Union["Player", str]] = None,
        **extra: Any,
    ) -> ParticleSpawner:
        """
        Throw particles into the world.

        1. A puff of sparks where something happened::

            >>> lt.particles.spawn(Point(10, 20, 30))

        2. In a colour, and more of them::

            >>> lt.particles.spawn(Point(10, 20, 30), color="#ffcc00", amount=300)

        3. A firework - flying apart, falling back down::

            >>> lt.particles.spawn(
            ...     Point(10, 30, 30), color="#ff6666", amount=400,
            ...     time=0.2, life=2, speed=7, spread=0.5, gravity=4, size=2,
            ... )

        4. Smoke that keeps rising until you stop it::

            >>> smoke = lt.particles.spawn(
            ...     Point(10, 20, 30), color="#888888", time=0, speed=1, spread=0.4
            ... )
            >>> smoke.stop()

        ``time`` and ``life`` are two different clocks and it is worth keeping them
        apart: ``time`` is how long *new* particles keep coming, ``life`` is how long
        *each one* lasts. A firework is a short ``time`` and a long ``life``; a
        campfire is ``time=0`` and a short ``life``.

        :param point: Where they come from.
        :param color: ``"#rrggbb"`` or an integer, or ``None`` for white.
        :param amount: How many, over the whole of ``time``.
        :param time: How long the spawner keeps sending, in seconds. ``0`` means it
            never stops on its own and needs :meth:`ParticleSpawner.stop`.
        :param life: How long one particle lasts, in seconds.
        :param size: How big they are. ``1`` is about a quarter of a block.
        :param speed: How fast they fly, in blocks per second, in any direction.
        :param spread: How far from ``point`` they may appear, in blocks.
        :param gravity: How hard they are pulled down, in blocks per second per second.
            Luanti's own gravity is about 10.
        :param glow: How much they shine in the dark, 0 to 14. The default is the
            brightest, so a night scene still shows them.
        :param texture: The image to use instead of Miney's spark - one of
            :attr:`lt.assets.textures <miney.Luanti.assets>`, for example.
        :param player: Only this player sees them. A :class:`~miney.Player` or a name.
        :param extra: Anything else the engine's ParticleSpawner takes, passed straight
            through: ``jitter``, ``drag``, ``attract``, ``collisiondetection``, the
            ``*_tween`` tables. A name the engine does not know is **ignored without a
            word**, so check it against Luanti's `lua_api.md` if nothing happens.
        :return: A :class:`ParticleSpawner`, to stop it with.
        :raises TypeError: If a value is of the wrong kind.
        :raises ValueError: If a number is out of range, or ``extra`` repeats something
            a parameter above already says.
        """
        definition = {
            "pos": _vector(point),
            "amount": int(_number(amount, "amount", minimum=1)),
            "time": _number(time, "time"),
            "exptime": _number(life, "life"),
            "size": _number(size, "size"),
            "glow": int(_number(glow, "glow")),
            "texture": _texture(texture, color),
        }
        if definition["glow"] > 14:
            raise ValueError(f"glow goes from 0 (dark) to 14 (bright), not {glow!r}.")

        spread = _number(spread, "spread")
        if spread:
            # A sphere around the point, which is what a burst looks like. A cube is
            # what you get from the engine's own pos range, and it shows.
            definition["radius"] = {"min": 0.0, "max": spread}

        speed = _number(speed, "speed")
        if speed:
            definition["vel"] = {
                "min": {"x": -speed, "y": -speed, "z": -speed},
                "max": {"x": speed, "y": speed, "z": speed},
            }

        gravity = _number(gravity, "gravity")
        if gravity:
            definition["acc"] = {"x": 0.0, "y": -gravity, "z": 0.0}

        if player is not None:
            name = getattr(player, "name", player)
            if not isinstance(name, str):
                raise TypeError(
                    f"player is one player or their name, as in lt.players.Steve, "
                    f"not {player!r}."
                )
            definition["playername"] = name

        for field, value in extra.items():
            if field in _OWNED:
                raise ValueError(
                    f'"{field}" is what Luanti calls it, and Miney already sends it: '
                    f"use the {_OWNED[field]} parameter instead."
                )
            definition[field] = value

        key = f"spawner-{next(self._keys)}"
        # The engine hands back a number, and asking for it would cost a server step per
        # burst. So the key is made here and Lua remembers which number it stands for -
        # in this session's own table, which the mod empties when the session ends.
        self.lt.lua.run(
            f"miney_spawners = miney_spawners or {{}} "
            f"miney_spawners[{self.lt.lua.dumps(key)}] = "
            f"minetest.add_particlespawner({self.lt.lua.dumps(definition)})",
            wait=False,
        )
        return ParticleSpawner(self, key)

    def stop_all(self) -> None:
        """
        End every spawner this session started.

        The one line to put at the end of a show, so nothing keeps smoking after it.

        .. code-block:: python

            lt.particles.stop_all()
        """
        self._delete(None)
