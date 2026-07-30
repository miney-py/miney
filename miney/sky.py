"""
The sky one player sees: its colour, the clouds, sun, moon, stars and the brightness.
"""
from typing import TYPE_CHECKING, Any, Optional

from .exceptions import PlayerOffline
# The same colours as on the screen, so "#ffcc00" means one thing in this library.
from .hud import _color

if TYPE_CHECKING:
    from .luanti import Luanti
    from .player import Player


def _colorspec(value: Any) -> str:
    """
    Turn a colour into the string form Luanti reads everywhere.

    :param value: ``"#rrggbb"``, ``"#rrggbbaa"`` or an integer.
    :return: A ColorSpec string, alpha and all.
    :raises ValueError: For anything that is not a colour.
    """
    number = _color(value)
    return f"#{number:08x}" if number > 0xFFFFFF else f"#{number:06x}"


def _flag(value: Any, name: str) -> bool:
    """
    :param value: What the property was set to.
    :param name: The property's name, for the error message.
    :return: The value, once it is really a bool.
    :raises TypeError: For anything else, ``1`` included.
    """
    if not isinstance(value, bool):
        raise TypeError(
            f"{name} is either True or False, not {value!r}."
        )
    return value



class Sky:
    """
    The sky one player sees, and everything hanging in it.

    Reached through :attr:`Player.sky <miney.Player.sky>` and never created directly::

        >>> p = lt.players.Steve
        >>> p.sky.color = "#101040"
        >>> p.sky.clouds = False
        >>> p.sky.brightness = 0.05
        >>> p.sky.reset()

    .. important::

        **This is what one player sees, not what the world is.** Luanti keeps these
        settings per player and sends them to that one client, so the world stays as
        bright as it was: torches burn the same, plants grow the same, and no mob
        spawns because of anything here.

        .. code-block:: python

            p.sky.brightness = 0.05   # Steve sees night. The world is still noon.
            lt.time_of_day = 0.0      # This is the one that brings the zombies.

    Every setting stays until something puts it back, long after your script has ended -
    :meth:`reset` is the way back. Nothing survives the player leaving the game.

    .. note::

        Some games paint the sky themselves, once a second, and VoxeLibre is one of
        them - that is how rain darkens the day and how the Nether is red. What you set
        here is laid over what that game decided, for this player alone: everybody else
        keeps their weather, and so do the parts of the sky you have not set.
    """

    def __init__(self, luanti: "Luanti", player: "Player"):
        """
        :param luanti: The parent :class:`~miney.Luanti` object.
        :param player: Whose sky this is.
        """
        self.lt = luanti
        #: Whose sky this is.
        self.player = player

    def __repr__(self) -> str:
        return f'<Luanti Sky for "{self.player.name}">'

    def _write(self, part: str, value: Any) -> None:
        """
        Set one part of this player's sky, and hold it there.

        The mod does both halves of that: it makes the engine call, and it remembers
        what was set so that a game which paints its own sky - VoxeLibre repaints every
        player about once a second - has this laid over its own answer for this player.
        Without it a colour was gone before the next line of a script ran.

        Each part keeps the fields it is not given, in the engine and in what the mod
        holds: ``set_sky{clouds = false}`` leaves the colour alone, so one property
        really is one call and nothing has to be read back first.

        :param part: ``"sky"``, ``"sun"``, ``"moon"``, ``"stars"`` or ``"ratio"``.
        :param value: The table the engine call takes, or the number for ``"ratio"``.
        """
        dumps = self.lt.lua.dumps
        self.lt.lua.run(
            f"miney_sky.hold({dumps(self.player.name)}, {dumps(part)}, {dumps(value)})",
            wait=False,
        )

    def _read(self, body: str) -> dict:
        """
        Ask the server about this player's sky.

        :param body: Lua returning a table, with ``online = true`` in it so that an
            answer of nothing can only mean the player is gone.
        :return: That table.
        :raises miney.exceptions.PlayerOffline: If the player is not in the game.
        """
        answer = self.lt.lua.run(
            f"local player = minetest.get_player_by_name("
            f"{self.lt.lua.dumps(self.player.name)}) "
            f"if not player then return nil end "
            f"{body}"
        )
        if not answer:
            raise PlayerOffline(
                f'"{self.player.name}" is not in the game, so there is no sky to look '
                f"at."
            )
        return answer

    @property
    def color(self) -> Optional[str]:
        """
        Get or set one flat colour for the whole sky.

        Setting this replaces Luanti's painted sky - the one that goes blue at noon and
        red at sunset - with a single colour that stays. Set it to ``None`` to get the
        painted sky back.

        The stars, sun and moon keep hanging in it, so a black sky is a night sky
        rather than an empty screen::

            >>> p.sky.color = "#101040"      # deep blue, all day
            >>> p.sky.color
            '#101040'
            >>> p.sky.color = None           # the game's own sky again
            >>> p.sky.color
            None

        :return: ``"#rrggbb"``, or ``None`` while the game paints the sky itself.
        :raises ValueError: If the value is not a colour.
        :raises miney.exceptions.PlayerOffline: When read for a player who left.
        """
        answer = self._read(
            "local s = player:get_sky(true) "
            "return {online = true, type = s.type, color = s.base_color}"
        )
        if answer.get("type") != "plain":
            return None
        rgb = answer.get("color") or {}
        return "#{:02x}{:02x}{:02x}".format(
            int(rgb.get("r", 0)), int(rgb.get("g", 0)), int(rgb.get("b", 0))
        )

    @color.setter
    def color(self, value: Optional[str]) -> None:
        if value is None:
            self._write("sky", {"type": "regular"})
        else:
            self._write("sky", {"type": "plain", "base_color": _colorspec(value)})

    @property
    def clouds(self) -> bool:
        """
        Get or set whether there are clouds.

        >>> p.sky.clouds = False

        :return: ``True`` if the player sees clouds.
        :raises TypeError: If the value is not ``True`` or ``False``.
        :raises miney.exceptions.PlayerOffline: When read for a player who left.
        """
        return bool(
            self._read(
                "local s = player:get_sky(true) "
                "return {online = true, clouds = s.clouds}"
            ).get("clouds")
        )

    @clouds.setter
    def clouds(self, value: bool) -> None:
        self._write("sky", {"clouds": _flag(value, "clouds")})

    @property
    def sun(self) -> bool:
        """
        Get or set whether the sun is in the sky.

        The morning glow on the horizon goes with it. Luanti draws that separately, and
        left on its own it keeps colouring the sunrise for a sun that is not there
        anymore.

        >>> p.sky.sun = False

        :return: ``True`` if the player sees the sun.
        :raises TypeError: If the value is not ``True`` or ``False``.
        :raises miney.exceptions.PlayerOffline: When read for a player who left.
        """
        return bool(
            self._read(
                "local s = player:get_sun() return {online = true, sun = s.visible}"
            ).get("sun")
        )

    @sun.setter
    def sun(self, value: bool) -> None:
        shown = _flag(value, "sun")
        self._write("sun", {"visible": shown, "sunrise_visible": shown})

    @property
    def moon(self) -> bool:
        """
        Get or set whether the moon is in the sky.

        >>> p.sky.moon = False

        :return: ``True`` if the player sees the moon.
        :raises TypeError: If the value is not ``True`` or ``False``.
        :raises miney.exceptions.PlayerOffline: When read for a player who left.
        """
        return bool(
            self._read(
                "local s = player:get_moon() return {online = true, moon = s.visible}"
            ).get("moon")
        )

    @moon.setter
    def moon(self, value: bool) -> None:
        self._write("moon", {"visible": _flag(value, "moon")})

    @property
    def stars(self) -> bool:
        """
        Get or set whether there are stars.

        They are there by day as well, just too faint to see against a bright sky.
        Turn the :attr:`brightness` down and they come out.

        >>> p.sky.stars = True

        :return: ``True`` if the player sees stars.
        :raises TypeError: If the value is not ``True`` or ``False``.
        :raises miney.exceptions.PlayerOffline: When read for a player who left.
        """
        return bool(
            self._read(
                "local s = player:get_stars() return {online = true, stars = s.visible}"
            ).get("stars")
        )

    @stars.setter
    def stars(self, value: bool) -> None:
        self._write("stars", {"visible": _flag(value, "stars")})

    @property
    def brightness(self) -> Optional[float]:
        """
        Get or set how bright the world looks to this player.

        ``0`` is the middle of the night and ``1`` is noon, whatever the clock says.
        ``None`` hands the daylight back to the day and night cycle.

        This is the one that makes a dark sky feel dark: :attr:`color` paints what is
        above the player, this dims everything below it.

        .. code-block:: python

            p.sky.brightness = 0.05     # night, at noon
            p.sky.brightness = None     # back to the time of day

        :return: A number between 0 and 1, or ``None`` while the day decides.
        :raises ValueError: If the value is outside 0 to 1.
        :raises TypeError: If the value is not a number.
        :raises miney.exceptions.PlayerOffline: When read for a player who left.
        """
        ratio = self._read(
            "return {online = true, ratio = player:get_day_night_ratio()}"
        ).get("ratio")
        # The engine keeps this as a 32 bit float, so 0.05 comes back as
        # 0.05000000074505806 and `sky.brightness == 0.05` is False right after setting
        # it. Six decimals is finer than anything an eye can tell apart on a 0 to 1
        # dimmer, and it makes the value that goes out the value that comes back.
        return None if ratio is None else round(float(ratio), 6)

    @brightness.setter
    def brightness(self, value: Optional[float]) -> None:
        if value is None:
            self._write("ratio", None)
            return
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(
                f"Brightness is a number between 0 (night) and 1 (noon), or None to "
                f"let the day decide. {value!r} is neither."
            )
        if not 0 <= value <= 1:
            raise ValueError(
                f"Brightness has to be between 0 (night) and 1 (noon), not {value!r}."
            )
        self._write("ratio", float(value))

    def reset(self) -> None:
        """
        Put back the sky the game shows by itself.

        Colour, clouds, sun, moon, stars and brightness, all in one go. Worth the last
        line of any script that changed the sky: a player left in an artificial night
        stays in it until they log out.

        .. code-block:: python

            p.sky.color = "#101040"
            p.sky.brightness = 0.05
            # ... the show ...
            p.sky.reset()

        In a game that paints its own sky - VoxeLibre does, for rain, for the Nether,
        for being underwater - this is also the line that hands that job back for this
        player. Nobody else's sky was ever affected, and nobody else's changes here.
        """
        self.lt.lua.run(
            f"miney_sky.release({self.lt.lua.dumps(self.player.name)})",
            wait=False,
        )
