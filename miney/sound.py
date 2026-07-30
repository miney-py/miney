"""
Noise: a click, a chime, a thunderclap, or music that plays until you stop it.
"""
from itertools import count
from typing import TYPE_CHECKING, Any, Optional, Union

# ponytail: the same two checks particles.py already does - a number with a range and a
# Point turned into a Lua table. One definition, imported rather than copied.
from .particles import _number, _vector

if TYPE_CHECKING:
    from .luanti import Luanti
    from .player import Player
    from .point import Point

#: What every named parameter of :meth:`Sound.play` is called once it reaches Luanti, so
#: that ``extra`` can say which parameter to use instead of a field it collides with.
_OWNED = {
    "gain": "gain", "pitch": "pitch", "fade": "fade", "loop": "loop",
    "pos": "point", "to_player": "player", "object": "follow",
    "start_time": "start", "max_hear_distance": "distance",
}


def _sound_name(name: Any) -> str:
    """
    :param name: What :meth:`Sound.play` was given as a sound.
    :return: The sound group name Luanti plays, without a file extension.
    :raises TypeError: If it is not a name.
    :raises ValueError: If it is empty, which Luanti reads as "play nothing".
    """
    if not isinstance(name, str):
        raise TypeError(
            f"A sound is named, as in \"default_dig_stone\", not {name!r}. "
            f"lt.assets.sounds has every name this server knows."
        )
    # A sound is played by its group name, so "x.ogg" and "x.3.ogg" are both "x". Nobody
    # should have to know that to pass the name lt.assets.upload() just handed back.
    if name.lower().endswith(".ogg"):
        name = name[:-4]
    if not name:
        raise ValueError(
            "An empty name plays nothing at all. lt.assets.sounds has every name this "
            "server knows."
        )
    return name


class PlayingSound:
    """
    A sound that is playing, and the way to end it.

    You never make one of these - :meth:`Sound.play` hands it back::

        >>> music = lt.sound.play("miney_low_random", loop=True)
        >>> music.fade_out(3)

    It is also a context manager, which is the tidier way to say the same thing::

        >>> with lt.sound.play("miney_low_random", loop=True):
        ...     build_the_thing()
        ...                                 # silent again on the way out, come what may
    """

    def __init__(self, sound: "Sound", key: str, gain: float):
        """
        :param sound: The :class:`Sound` this one came from.
        :param key: How the server knows this sound.
        :param gain: How loud it was started, which is what a fade counts down from.
        """
        self._sound = sound
        #: How the server knows this sound.
        self.key = key
        #: How loud it was started.
        self.gain = gain

    def __repr__(self) -> str:
        return f'<Luanti PlayingSound "{self.key}">'

    def __enter__(self) -> "PlayingSound":
        return self

    def __exit__(self, *_) -> None:
        self.stop()

    def stop(self) -> None:
        """
        Stop it now.

        Stopping one twice is not an error, and neither is stopping one that finished on
        its own - only a sound made with ``loop=True`` really needs this.

        .. code-block:: python

            music = lt.sound.play("miney_low_random", loop=True)
            # ... a while later ...
            music.stop()
        """
        self._sound._end(self.key)

    def fade_out(self, seconds: float = 1.0) -> None:
        """
        Turn it down to nothing over this many seconds, then stop it.

        Kinder than :meth:`stop` for anything a player has been listening to::

            >>> music = lt.sound.play("miney_low_random", loop=True, gain=0.5)
            >>> music.fade_out(3)

        :param seconds: How long the fade takes. Must be more than 0 - to end it at once
            use :meth:`stop`.
        :raises ValueError: If ``seconds`` is 0 or less.
        """
        seconds = _number(seconds, "seconds")
        if not seconds:
            raise ValueError(
                "A fade over 0 seconds is not a fade. Use stop() to end it at once."
            )
        # Luanti fades by gain per second, not for a number of seconds, so how loud this
        # one started decides how fast it has to go down to arrive at nothing on time.
        self._sound._end(self.key, step=self.gain / seconds)


class Sound:
    """
    Noise: a click, a chime, or music that plays until you stop it.

    Reached through :attr:`lt.sound <miney.Luanti.sound>` and never created directly::

        >>> lt.sound.play("miney_power_up_1")
        <Luanti PlayingSound "sound-1">

    A sound is named, not filed: ``"default_dig_stone"`` is a name the game answers to,
    and :attr:`lt.assets.sounds <miney.Assets.sounds>` is where to find one with TAB.
    Given a :class:`~miney.Point` it comes from that place and fades with distance;
    without one it is equally loud everywhere, which is what music wants.

    Every name beginning with ``miney_`` comes with Miney's own mod and works in any
    game - 47 CC0 effects by `Kenney Vleugels <https://kenney.nl/assets/digital-audio>`_,
    so an example has something to play before you have gone looking for a name.

    .. important::

        A sound with ``loop=True`` keeps playing after your script has ended. Somebody
        has to stop it - :meth:`PlayingSound.stop`, :meth:`stop_all`, or your session
        ending, because Miney's mod clears out what a connection left behind.
    """

    def __init__(self, luanti: "Luanti"):
        """
        :param luanti: The parent :class:`~miney.Luanti` object.
        """
        self.lt = luanti
        self._keys = count(1)

    def __repr__(self) -> str:
        return "<Luanti Sound>"

    def _end(self, key: Optional[str], step: float = 0.0) -> None:
        """
        :param key: The sound to end, or ``None`` for every one of them.
        :param step: How much gain to lose per second, or ``0`` to cut it off.
        """
        # A target gain of 0 makes the server drop the sound as well, so a fade really
        # ends it rather than leaving something inaudible running (server.cpp, fadeSound).
        if step:
            # Rounded because 0.6 / 3 writes itself as 0.19999999999999998, and this
            # line ends up in a server log somebody may have to read.
            call = f"minetest.sound_fade(id, {round(step, 6)}, 0)"
        else:
            call = "minetest.sound_stop(id)"

        if key is None:
            self.lt.lua.run(
                f"if miney_sounds then for _, id in pairs(miney_sounds) do "
                f"{call} end miney_sounds = {{}} end",
                wait=False,
            )
            return
        name = self.lt.lua.dumps(key)
        self.lt.lua.run(
            f"if miney_sounds and miney_sounds[{name}] then "
            f"local id = miney_sounds[{name}] {call} "
            f"miney_sounds[{name}] = nil end",
            wait=False,
        )

    def play(
        self,
        name: str,
        *,
        gain: float = 1.0,
        pitch: float = 1.0,
        loop: bool = False,
        point: Optional["Point"] = None,
        player: Optional[Union["Player", str]] = None,
        follow: Optional[Union["Player", str]] = None,
        fade: float = 0.0,
        start: float = 0.0,
        distance: Optional[float] = None,
        **extra: Any,
    ) -> PlayingSound:
        """
        Play a sound.

        1. Everywhere, once::

            >>> lt.sound.play("miney_power_up_1")

        2. At a place, so it gets quieter the further away you are::

            >>> lt.sound.play("miney_power_up_1", point=Point(10, 20, 30))

        3. Music, until you stop it::

            >>> music = lt.sound.play("miney_low_random", loop=True, gain=0.4)
            >>> music.fade_out(3)

        4. In one player's ears only, half as deep::

            >>> lt.sound.play("miney_power_up_1", player=lt.players.Steve, pitch=0.5)

        5. Travelling with a player, for everybody to hear::

            >>> lt.sound.play("miney_power_up_1", follow=lt.players.Steve)

        6. Your own::

            >>> lt.sound.play(lt.assets.upload(Path("fanfare.ogg")))

        ``player`` and ``follow`` sound alike and are not: ``player`` is *who hears it*,
        ``follow`` is *where it comes from*. They combine, so one player can hear a sound
        that another player carries.

        :param name: The sound, from :attr:`lt.assets.sounds <miney.Assets.sounds>` or
            from :meth:`lt.assets.upload() <miney.Assets.upload>`. A trailing ``.ogg`` is
            dropped for you.
        :param gain: How loud, where ``1`` is the sound's own level. Above ``1`` a
            placed sound does not get louder, it gets *further* - the volume is measured
            three blocks away.
        :param pitch: How deep. ``0.5`` is an octave down, ``2`` an octave up.
        :param loop: Start again at the end, for ever. Needs
            :meth:`PlayingSound.stop`.
        :param point: Where it comes from. Without one it is equally loud everywhere and
            follows nobody, which is what music wants.
        :param player: Only this player hears it. A :class:`~miney.Player` or a name.
        :param follow: The sound travels with this player. A :class:`~miney.Player` or a
            name. Cannot be combined with ``point``.
        :param fade: Fade *in* over this long, in gain per second. ``0.5`` takes two
            seconds to reach ``gain``.
        :param start: Start this many seconds into the sound instead of at the
            beginning.
        :param distance: How far away it can still be heard, in blocks. Luanti's own
            answer is 32. Needs ``point`` or ``follow``.
        :param extra: Anything else Luanti's sound parameter table takes, passed
            straight through - ``exclude_player``, for example. A name the engine does
            not know is **ignored without a word**, so check it against Luanti's
            `lua_api.md` if nothing happens.
        :return: A :class:`PlayingSound`, to stop it with.
        :raises TypeError: If a value is of the wrong kind.
        :raises ValueError: If a number is out of range, if ``point`` and ``follow`` are
            given together, if ``distance`` has no place to measure from, or if ``extra``
            repeats something a parameter above already says.
        """
        if point is not None and follow is not None:
            raise ValueError(
                "A sound is either at a place or on a player, not both. Drop point= to "
                "let it travel with the player, or drop follow= to nail it down."
            )

        params: dict = {
            "gain": _number(gain, "gain"),
            "pitch": _number(pitch, "pitch"),
        }
        if not params["pitch"]:
            raise ValueError("pitch is a factor, so it has to be more than 0.")
        if loop:
            params["loop"] = True
        if fade:
            params["fade"] = _number(fade, "fade")
        if start:
            params["start_time"] = _number(start, "start")
        if point is not None:
            params["pos"] = _vector(point)
        if player is not None:
            params["to_player"] = _player_name(player, "player")

        if distance is not None:
            if point is None and follow is None:
                raise ValueError(
                    "distance is how far away a sound can still be heard, and a sound "
                    "with no place is heard everywhere. Give it a point= or a follow=."
                )
            params["max_hear_distance"] = _number(distance, "distance")

        for field, value in extra.items():
            if field in _OWNED:
                raise ValueError(
                    f'"{field}" is what Luanti calls it, and Miney already sends it: '
                    f"use the {_OWNED[field]} parameter instead."
                )
            params[field] = value

        key = f"sound-{next(self._keys)}"
        dumps = self.lt.lua.dumps
        spec = dumps(_sound_name(name))
        # The engine hands back a number, and asking for it would cost a server step per
        # sound. So the key is made here and Lua remembers which number it stands for -
        # in this session's own table, which the mod empties when the session ends.
        store = f"miney_sounds = miney_sounds or {{}} miney_sounds[{dumps(key)}] = "

        if follow is None:
            code = f"{store}minetest.sound_play({spec}, {dumps(params)})"
        else:
            # An ObjectRef cannot travel through dumps(), so the player is looked up on
            # the other side. One who left in the meantime simply makes no sound, which
            # beats an error from inside the engine.
            code = (
                f"local who = minetest.get_player_by_name("
                f"{dumps(_player_name(follow, 'follow'))}) "
                f"if who then local p = {dumps(params)} p.object = who "
                f"{store}minetest.sound_play({spec}, p) end"
            )
        self.lt.lua.run(code, wait=False)
        return PlayingSound(self, key, params["gain"])

    def stop_all(self) -> None:
        """
        Stop every sound this session started.

        The one line to put at the end of a show, so nothing keeps playing after it.

        .. code-block:: python

            lt.sound.stop_all()
        """
        self._end(None)


def _player_name(player: Any, parameter: str) -> str:
    """
    :param player: A :class:`~miney.Player` or a player's name.
    :param parameter: Which parameter it came from, for the error message.
    :return: The name.
    :raises TypeError: For anything else.
    """
    name = getattr(player, "name", player)
    if not isinstance(name, str):
        raise TypeError(
            f"{parameter} is one player or their name, as in lt.players.Steve, "
            f"not {player!r}."
        )
    return name
