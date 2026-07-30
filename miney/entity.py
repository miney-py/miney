"""
The things in the world that are not blocks: mobs, dropped items, boats.
"""
from typing import TYPE_CHECKING

from .point import Point

if TYPE_CHECKING:
    from .luanti import Luanti


#: Everything standing within a radius, as plain values.
#:
#: ``get_objects_inside_radius`` and not the newer ``objects_inside_radius`` iterator:
#: the iterator arrived after 5.9, and the danger it guards against - an object going
#: invalid while you punch its neighbour - cannot happen here, because this reads and
#: returns without touching anything.
#:
#: Players come back from the engine as well. They are dropped here rather than in
#: Python so that nothing that was not asked for travels.
_NEAR_LUA = """
local center = {center}
local want_players = {players}
local found = {{}}
for _, obj in ipairs(minetest.get_objects_inside_radius(center, {radius})) do
    local pos = obj:get_pos()
    if pos then
        local player_name = obj:get_player_name() or ""
        local is_player = player_name ~= ""
        local name = player_name
        if not is_player then
            local entity = obj:get_luaentity()
            name = (entity and entity.name) or ""
        end
        if not is_player or want_players then
            found[#found + 1] = {{name = name, x = pos.x, y = pos.y, z = pos.z,
                                  hp = obj:get_hp(), is_player = is_player}}
        end
    end
end
return found
"""


class Entity:
    """
    Something standing in the world that is not a block: a mob, a dropped item, a boat.

    You do not create this yourself - it is what
    :meth:`lt.entities.near() <miney.Entities.near>` answers with.

    It is a **snapshot**, taken when you asked. The cow it describes walks on; reading
    :attr:`position` a minute later still gives where it was, so ask again rather than
    keeping one around::

        >>> for thing in lt.entities.near(player.position, radius=20):
        ...     print(thing.name, "is", round(player.position.distance(thing.position)), "away")

    :param name: What it is, e.g. ``"mobs_mc:cow"``, or the player's name.
    :param position: Where it stood.
    :param hp: How much health it had left.
    :param is_player: Whether it is a person rather than a mob.
    """

    def __init__(self, name: str, position: Point, hp: float, is_player: bool):
        self._name = name
        self._position = position
        self._hp = hp
        self._is_player = is_player

    @property
    def name(self) -> str:
        """
        What this is.

        A mob or an item carries the name its mod gave it, ``"mobs_mc:cow"`` or
        ``"__builtin:item"`` for anything lying on the ground. A player carries their
        player name instead.

        :return: The name.
        """
        return self._name

    @property
    def position(self) -> Point:
        """
        Where it stood when you asked.

        :return: A :class:`~miney.Point`, so it goes straight into
            :meth:`player.move() <miney.Player.move>` or
            :meth:`lt.particles.spawn() <miney.Particles.spawn>`.
        """
        return self._position

    @property
    def hp(self) -> float:
        """
        How much health it had left. Most mobs start at 10 or 20, an item is 0.

        :return: The health.
        """
        return self._hp

    @property
    def is_player(self) -> bool:
        """
        Whether this is a person rather than a mob or an item.

        Only ever ``True`` when you asked for players with
        ``lt.entities.near(..., players=True)``.

        :return: ``True`` for a player.
        """
        return self._is_player

    def __repr__(self) -> str:
        return (f'<Luanti Entity "{self._name}" at '
                f'({self._position.x:g}, {self._position.y:g}, {self._position.z:g})>')


class Entities:
    """
    Everything in the world that is not a block: mobs, dropped items, boats.

    Miney could not see a single one of them before. This is how a script notices that
    something is *there* - which is what anything that reacts to the world needs first.

    You do not create this class yourself, it is reached through
    :attr:`lt.entities <miney.Luanti.entities>`.

    :param luanti: The parent :class:`~miney.Luanti` object.
    """

    def __init__(self, luanti: 'Luanti'):
        self.lt = luanti

    def near(self, point: Point, radius: int = 10,
             players: bool = False) -> list[Entity]:
        """
        Everything standing within a radius of a point.

        :Examples:

            What is around the player?

            >>> player = lt.players[0]
            >>> for thing in lt.entities.near(player.position, radius=20):
            ...     print(thing)
            <Luanti Entity "mobs_mc:cow" at (12, 8, -3)>
            <Luanti Entity "__builtin:item" at (9, 8, 1)>

            Are we being watched?

            >>> if lt.entities.near(player.position, radius=5):
            ...     lt.chat.send_to_player(player.name, "Something is close.")

            Count the cows:

            >>> from miney import Point
            >>> herd = [t for t in lt.entities.near(Point(0, 10, 0), radius=50)
            ...         if t.name == "mobs_mc:cow"]
            >>> len(herd)
            7

        **Players are left out** unless you ask for them. A player is always within any
        radius of themselves, and finding yourself in the answer to *"what is near me"*
        is a surprise nobody needs in their first loop.

        Everything on the ground - dropped blocks, dropped tools - is called
        ``"__builtin:item"``, whatever it happens to be. Which item it is lives
        somewhere Miney does not read yet.

        :param point: The middle of the search.
        :param radius: How far to look, in blocks. 10 by default.
        :param players: Include people as well as mobs.
        :return: Every :class:`~miney.Entity` found, or an empty list.
        :raises TypeError: If ``point`` is not a :class:`~miney.Point`.
        :raises ValueError: If ``radius`` is not a positive number.
        """
        if not isinstance(point, Point):
            raise TypeError(
                f"'point' must be a Point, got {type(point).__name__}: "
                f"lt.entities.near(lt.players[0].position, radius=20)"
            )
        if isinstance(radius, bool) or not isinstance(radius, (int, float)) \
                or radius < 1:
            raise ValueError(
                f"'radius' is how many blocks around the point to look in and has to "
                f"be at least 1, got {radius!r}."
            )

        found = self.lt.lua.run(
            _NEAR_LUA.format(
                center=self.lt.lua.dumps({"x": point.x, "y": point.y, "z": point.z}),
                radius=float(radius),
                players="true" if players else "false",
            ),
            timeout=30,
        )
        return [Entity(one["name"], Point(one["x"], one["y"], one["z"]),
                       one["hp"], one["is_player"])
                for one in found or []]

    def __repr__(self) -> str:
        return '<Luanti entity functions>'
