import time
from typing import Iterable, List, TYPE_CHECKING, Optional
from .exceptions import PlayerNotFoundError, PlayerOffline, LuaError
from .point import Point
from .vector import Vector
if TYPE_CHECKING:
    from .luanti import Luanti
    from .node import Node


class PrivilegeManager:
    """
    Manages player privileges by providing a list-like interface.

    This object is returned by the :attr:`~miney.Player.privileges`
    property and is not meant to be instantiated directly.
    """
    def __init__(self, player: 'Player'):
        self._player = player

    def _get_all(self) -> dict:
        """Fetches all privileges from the server."""
        return self._player.lt.lua.run(f'return minetest.get_player_privs("{self._player.name}")') or {}

    def list(self) -> List[str]:
        """
        Return a list of all active privileges for the player.

        :return: A list of privilege strings.
        """
        return [priv for priv, active in self._get_all().items() if active]

    def __repr__(self) -> str:
        return f"<PrivilegeManager for '{self._player.name}': {self.list()}>"

    def __iter__(self) -> Iterable[str]:
        return iter(self.list())

    def __contains__(self, privilege: str) -> bool:
        return self._get_all().get(privilege, False)

    def __len__(self) -> int:
        return len(self.list())

    def append(self, privilege: str):
        """
        Grant a new privilege to the player.

        :param privilege: The name of the privilege to grant.
        """
        if not isinstance(privilege, str):
            raise TypeError("Privilege must be a string.")

        self._player.lt.lua.run(
            f"""
            local privs = minetest.get_player_privs("{self._player.name}") or {{}}
            privs["{privilege}"] = true
            minetest.set_player_privs("{self._player.name}", privs)
            """
        )

    def remove(self, privilege: str):
        """
        Revoke a privilege from the player.

        :param privilege: The name of the privilege to revoke.
        :raises ValueError: if the privilege is not in the list.
        """
        if not isinstance(privilege, str):
            raise TypeError("Privilege must be a string.")
        if privilege not in self:
            raise ValueError(f"Privilege '{privilege}' not found.")

        self._player.lt.lua.run(
            f"""
            local privs = minetest.get_player_privs("{self._player.name}") or {{}}
            privs["{privilege}"] = nil
            minetest.set_player_privs("{self._player.name}", privs)
            """
        )


class Player:
    """
    A player of the Luanti server.
    """
    def __init__(self, luanti: 'Luanti', name):
        """
        Initialize the player object.

        :param luanti: Parent Luanti object
        :param name: Player name
        """
        from .hud import Hud
        from .inventory import Inventory
        from .sky import Sky
        from .storage import PlayerStorage
        self.lt = luanti
        self.name = name
        
        # get user data: password hash, last login, privileges
        data = self.lt.lua.run("return minetest.get_auth_handler().get_auth('{}')".format(self.name))
        if data and all(k in data for k in ("password", "last_login", "privileges")):  # if we have all keys
            self.password = data["password"]
            self.last_login = data["last_login"]
            self.privileges = data["privileges"]
        else:
            raise PlayerNotFoundError(f"There is no player {self.name!r} on this server.")

        self.inventory: Inventory = Inventory(luanti, self)
        """Manipulate player's inventory.
        
        :Example to add 99 dirt to player "IloveDirt"'s inventory:
        
        >>> import miney
        >>> lt = miney.Luanti()
        >>> lt.players.IloveDirt.inventory.add(lt.nodes.names.default.dirt, 99)      
            
        :Example to remove 99 dirt from player "IhateDirt"'s inventory:
        
        >>> import miney
        >>> lt = miney.Luanti()
        >>> lt.players.IhateDirt.inventory.remove(lt.nodes.names.default.dirt, 99)
        """

        self.hud: Hud = Hud(luanti, self)
        """What this player sees on their screen, on top of the world.

        A chat message scrolls away; this stays until something takes it down.

        :Example, a message and a score that keeps counting:

        >>> import miney
        >>> lt = miney.Luanti()
        >>> lt.players.Steve.hud.text("Welcome!")
        >>> score = lt.players.Steve.hud.text("Score: 0", position="top left")
        >>> score.text = "Score: 7"

        See :class:`~miney.hud.Hud` for waypoints, images, bars, and for switching off
        what Luanti draws by itself.
        """

        self.sky: Sky = Sky(luanti, self)
        """The sky this player sees: its colour, the clouds, sun, moon, stars and how
        bright everything looks.

        :Example, night at noon:

        >>> import miney
        >>> lt = miney.Luanti()
        >>> lt.players.Steve.sky.color = "#101040"
        >>> lt.players.Steve.sky.brightness = 0.05
        >>> lt.players.Steve.sky.reset()

        Only this player sees it - the world stays as bright as it was, and no mob
        spawns because of it. :attr:`lt.time_of_day <miney.Luanti.time_of_day>` is the
        one that really makes it night. See :class:`~miney.sky.Sky`.
        """

        self.storage: PlayerStorage = PlayerStorage(self)
        """What you want to remember about this one player, used like a dictionary.

        It stays with them after they log out and after the server restarts, which
        nothing else in a script does.

        :Example, counting somebody's visits:

        >>> import miney
        >>> lt = miney.Luanti()
        >>> player = lt.players.Steve
        >>> player.storage["visits"] = str(int(player.storage.get("visits", "0")) + 1)
        >>> lt.chat.send_to_player(player.name, f"Visit number {player.storage['visits']}")

        Keys and values are strings, the same as :attr:`lt.storage
        <miney.Luanti.storage>`, which is the version for the whole world. See
        :class:`~miney.storage.PlayerStorage`.
        """

    def __repr__(self):
        return '<Luanti Player "{}">'.format(self.name)

    @property
    def is_online(self) -> bool | None:
        """
        Returns the online status of this player.

        Asked of the server rather than read from a list the client keeps, because
        Miney does not always have a client: connected to a world on this computer it
        is not in the game at all, and there is no player list of its own to consult.

        :return: True or False
        """
        return bool(self.lt.lua.run(
            f"return minetest.get_player_by_name({self.lt.lua.dumps(self.name)}) ~= nil"
        ))

    @property
    def position(self) -> Point:
        """
        Get or set the players current position.

        To place a player on top of a specific node, add 0.5 to the y value and his feet will touch this node.
        A player needs two blocks in the y axis (he's around 1,5 node tall), or he is stuck.

        :return: :class:`miney.Point`
        """
        try:
            return Point(
                **self.lt.lua.run("return minetest.get_player_by_name('{}'):get_pos()".format(self.name))
            )
        except LuaError:
            raise PlayerOffline("The player has no position, he could be offline")

    @position.setter
    def position(self, values: Point) -> None:
        """
        Set player position
        :param values:
        :return: None
        """
        self.lt.lua.run(
            "minetest.get_player_by_name('{}'):set_pos({{x = {}, y = {}, z = {}}})".format(
                self.name,
                values.x,
                values.y,
                values.z
            ),
            wait=False,
        )

    def move(
        self,
        destination: Optional[Point] = None,
        distance: Optional[float] = None,
        look_at: Optional[Point] = None,
        yaw: Optional[float] = None,
        pitch: Optional[float] = None,
        smooth: bool = False,
        duration: float = 1.0,
        step_interval: float = 0.05,
        wait: bool = False,
    ):
        """
        Moves the player and/or changes their look direction, with an option for smooth animation.

        This versatile function can perform several actions:
        1.  Instantly teleport the player (`smooth=False`).
        2.  Instantly change the player's look direction (`smooth=False`).
        3.  Animate the player's movement to a new location (`smooth=True`).
        4.  Animate the player's view to a new orientation (`smooth=True`).
        5.  Combine movement and look changes, either instantly or animated.

        **Examples:**

        .. code-block:: python

            import miney
            from miney.point import Point
            import math

            lt = miney.Luanti()
            player = lt.players["some_player"]

            # 1. Instant teleport to a specific coordinate
            player.move(destination=Point(10, 20, 30))

            # 2. Smoothly fly the player to a destination over 3 seconds
            player.move(destination=Point(50, 40, 50), smooth=True, duration=3)

            # 3. Instantly make the player look at a point
            player.move(look_at=Point(0, 20, 0))

            # 4. Smoothly turn the player to face North (yaw=PI) over 2 seconds
            player.move(yaw=math.pi, smooth=True, duration=2)

            # 5. Move 10 nodes forward smoothly
            player.move(distance=10, smooth=True)

            # 6. Smoothly move to a destination while turning to look at another point
            player.move(
                destination=Point(100, 25, 100),
                look_at=Point(0, 20, 0),
                smooth=True,
                duration=5
            )

            # 7. Fly there and only carry on once the player has arrived
            player.move(destination=Point(100, 25, 100), smooth=True, duration=5, wait=True)
            lt.chat.send_to_all("Made it!")

        .. note::

            A smooth move returns straight away, so the script keeps running while the
            player is still travelling. That is usually what you want - it is how a
            camera flies over a building site while the building goes on. Use
            ``wait=True`` when the next line depends on the player having arrived.

            **A second smooth move on the same player replaces the first.** Two of them
            at once used to drag the player between two paths and arrive at neither.

        :param destination: The target position as a :class:`~miney.point.Point`.
        :param distance: The distance to move forward (alternative to `destination`).
        :param look_at: A :class:`~miney.point.Point` to look at (alternative to `yaw`/`pitch`).
        :param yaw: The final horizontal look angle (yaw) in radians. The angle is measured
                    counter-clockwise from the positive Z-axis (South). Common values are:
                    - ``0``: South (+Z)
                    - ``math.pi / 2``: East (+X)
                    - ``math.pi``: North (-Z)
                    - ``3 * math.pi / 2``: West (-X)
        :param pitch: The final vertical look angle (pitch) in radians. It ranges from
                      ``-math.pi / 2`` (looking straight up) to ``math.pi / 2``
                      (looking straight down). ``0`` is looking horizontally forward.
        :param smooth: If ``True``, the action is animated over `duration`. If ``False``, it's instant.
        :param duration: The total time for the animation in seconds (if `smooth=True`).
        :param step_interval: The time between each animation step (if `smooth=True`).
        :param wait: If ``True``, block until the animation has finished. Needs
                     ``smooth=True``. Waiting is not the same as
                     ``time.sleep(duration)``: a step is scheduled for the *next* server
                     frame, never sooner, so an animation always takes at least its
                     duration and under load a little longer.
        :raises ValueError: If conflicting or no parameters are provided, or if ``wait``
                            is used without ``smooth``.
        """
        if all(p is None for p in [destination, distance, look_at, yaw, pitch]):
            raise ValueError("At least one action (destination, distance, look_at, yaw, pitch) must be provided.")
        if destination is not None and distance is not None:
            raise ValueError("Provide either 'destination' or 'distance', but not both.")
        if look_at is not None and (yaw is not None or pitch is not None):
            raise ValueError("Provide either 'look_at' or 'yaw'/'pitch', but not both.")
        if wait and not smooth:
            raise ValueError(
                "'wait' needs 'smooth=True'. Without an animation there is nothing to "
                "wait for - the player is already there when move() returns."
            )

        params = {}
        if destination:
            params["destination"] = destination
        if distance is not None:
            params["distance"] = distance
        if look_at:
            params["look_at"] = look_at
        if yaw is not None:
            params["yaw"] = yaw
        if pitch is not None:
            params["pitch"] = pitch

        if smooth:
            params["duration"] = duration
            params["step_interval"] = step_interval
            params_lua = self.lt.lua.dumps(params)
            lua_code = f"""
            local player = minetest.get_player_by_name('{self.name}')
            if player then
                smooth_move(player, {params_lua})
            end
            """
            self.lt.lua.run(lua_code, wait=False)
            if wait:
                self._wait_for_animation()
        else:
            # Instantaneous action
            lua_parts = []
            if "destination" in params:
                lua_parts.append(f"player:set_pos({self.lt.lua.dumps(params['destination'])})")
            elif "distance" in params:
                # Calculate target position instantly
                start_pos = self.position
                look_dir = self.look_dir
                target_pos = start_pos + (look_dir * params['distance'])
                lua_parts.append(f"player:set_pos({self.lt.lua.dumps(target_pos)})")

            if "look_at" in params:
                # Luanti has no set_look_dir - only set_look_horizontal and
                # set_look_vertical - so the direction has to become two angles first.
                # vector.dir_to_rotation returns them as {x = pitch, y = yaw}, which is
                # exactly what smooth_move() in the mod already does for the animated
                # path; doing the same here keeps instant and smooth in agreement.
                #
                # The direction is measured from where the player ends up rather than
                # from where they started, so "teleport there and look at this" points
                # at the thing instead of past it.
                # The pitch is negated. The two halves of this disagree about which way
                # is up: vector.dir_to_rotation returns asin(direction.y), positive when
                # the direction points upwards, while set_look_vertical documents
                # "positive is downwards". Feeding one straight into the other aims the
                # camera at the mirror image of the target - correct compass bearing,
                # inverted tilt - which is a 90 degree error when looking 45 degrees up.
                lua_parts.append(
                    f"local rot = vector.dir_to_rotation(vector.direction("
                    f"player:get_pos(), {self.lt.lua.dumps(params['look_at'])})) "
                    f"player:set_look_horizontal(rot.y) "
                    f"player:set_look_vertical(-rot.x)"
                )
            else:
                if "yaw" in params:
                    lua_parts.append(f"player:set_look_horizontal({params['yaw']})")
                if "pitch" in params:
                    lua_parts.append(f"player:set_look_vertical({params['pitch']})")

            if lua_parts:
                self.lt.lua.run(f"local player = minetest.get_player_by_name('{self.name}'); if player then {' '.join(lua_parts)} end")

    #: How often :meth:`move` with ``wait=True`` asks whether the animation is over. The
    #: animation itself advances every ``step_interval``, so asking faster than that
    #: would spend round trips on an answer that cannot have changed.
    _WAIT_POLL_INTERVAL = 0.05

    def _wait_for_animation(self) -> None:
        """
        Block until this player's smooth animation has finished.

        Asked, not pushed. The alternative is for the mod to send a message when the
        last frame runs, and that message would arrive on the callback channel, which
        one thread dispatches. Waiting inside a chat command handler would then wait for
        something that cannot be delivered until the handler returns - a deadlock a
        beginner has no way to see coming. Polling blocks only the caller.
        """
        key = self.lt.lua.dumps(f"move:{self.name}")
        while self.lt.lua.run(f"return miney_task_busy({key})"):
            time.sleep(self._WAIT_POLL_INTERVAL)

    @property
    def speed(self) -> int:
        """
        Get or set the players speed. Default is 1.

        :return: Float
        """
        return self.lt.lua.run(
            "return minetest.get_player_by_name('{}'):get_physics_override()".format(self.name))["speed"]

    @speed.setter
    def speed(self, value: int):
        self.lt.lua.run(
            "return minetest.get_player_by_name('{}'):set_physics_override({{speed = {}}})".format(self.name, value),
            wait=False)

    @property
    def jump(self):
        """
        Get or set the players jump height. Default is 1.

        :return: Float
        """
        return self.lt.lua.run(
            "return minetest.get_player_by_name('{}'):get_physics_override()".format(self.name))["jump"]

    @jump.setter
    def jump(self, value):
        self.lt.lua.run(
            "return minetest.get_player_by_name('{}'):set_physics_override({{jump = {}}})".format(self.name, value),
            wait=False)

    @property
    def gravity(self):
        """
        Get or set the players gravity. Default is 1.

        :return: Float
        """
        return self.lt.lua.run(
            "return minetest.get_player_by_name('{}'):get_physics_override()".format(self.name))["gravity"]

    @gravity.setter
    def gravity(self, value):
        self.lt.lua.run(
            "return minetest.get_player_by_name('{}'):set_physics_override({{gravity = {}}})".format(self.name, value),
            wait=False)

    #: Where :meth:`hold` writes down the physics and the armor groups it takes away, in
    #: the player's own metadata. Metadata survives a disconnect, so a script that dies
    #: mid-hold still leaves a way back.
    _HOLD_KEY = "miney:before_hold"

    #: What the Lua answers when this player is not in the game. A byte no name and no
    #: stored text can contain, so it can never be confused with a real answer.
    _OFFLINE = "\0offline"

    def _ask(self, body: str, wait: bool = True):
        """
        Run Lua with this player bound to the name ``player``, or say they are not there.

        Every property below needs the same three lines in front of it, and every one of
        them has to fail loudly rather than quietly do nothing - a script that thinks it
        set something is worse off than one that got an error.

        :param body: Lua, using ``player``.
        :param wait: Whether to wait for the answer. ``False`` gives up the offline
                     check with it, so only for writes that are worth the speed.
        :return: What the Lua returned.
        :raises ~miney.exceptions.PlayerOffline: If the player is not in the game.
        """
        answer = self.lt.lua.run(
            f"local player = minetest.get_player_by_name({self.lt.lua.dumps(self.name)}) "
            f"if not player then return {self.lt.lua.dumps(self._OFFLINE)} end "
            f"{body}",
            wait=wait,
        )
        if answer == self._OFFLINE:
            raise PlayerOffline(f"There is no player {self.name!r} in the game.")
        return answer

    @property
    def held(self) -> bool:
        """
        Whether this player is currently held by :meth:`hold`.

        Read-only. Giving physics back is :meth:`release`, and it has an ordering trap
        that is worth reading before you use it.

        .. code-block:: python

            player.hold()
            print(player.held)      # True
            player.release()
            print(player.held)      # False

        :return: ``True`` while a hold is on, ``False`` otherwise.
        :raises ~miney.exceptions.PlayerOffline: if the player is not in the game.
        """
        return bool(self._ask(
            f"return player:get_meta():get_string("
            f"{self.lt.lua.dumps(self._HOLD_KEY)}) ~= \"\""
        ))

    def hold(self) -> None:
        """
        Hold this player in mid-air and stop the world from hurting them.

        The player floats where they are and takes no damage - no fall, no drowning, no
        mob. :meth:`release` gives all of it back.

        This is what you want around a :meth:`move`. Teleporting or flying a player to a
        point above ground ends in a fall, and in some games - VoxeLibre among them - a
        fall from camera height is fatal.

        .. code-block:: python

            import miney
            from miney import Point

            lt = miney.Luanti()
            player = lt.players["Steve"]

            player.hold()
            player.move(destination=Point(200, 80, 200), smooth=True, duration=5, wait=True)
            lt.chat.send_to_all("Look down!")

            player.move(destination=Point(200, 12, 200))    # somewhere solid, first
            player.release()

        The player can still walk and jump while held, they simply do it in the air. Use
        :attr:`noclip` if you also want them to pass through walls.

        .. important::
            Read :meth:`release` before you use this. Handing physics back over thin air
            is the very fall this was meant to prevent.

        .. note::
            A player who is already falling keeps falling, more slowly - switching gravity
            off takes away the acceleration, not the speed they picked up on the way down.
            They survive the landing, because being held also means taking no damage. Hold
            first, move second, and it does not come up.

        :return: None
        :raises ~miney.exceptions.PlayerOffline: if the player is not in the game.
        """
        # What is taken away is written down first, so that release() puts back what this
        # game gave the player instead of a guess - the same reason and the same place as
        # `invisible`. Only if there is no record yet: a second hold() must not overwrite
        # the real values with the held ones.
        #
        # Two engine calls, two different habits, and they are the reason gravity is
        # stored as one number while the armor groups are stored whole:
        # set_physics_override merges field by field (l_object.cpp:1900-1916), so
        # {gravity = 0} leaves the speed and the jump the user set alone. set_armor_groups
        # replaces the list outright (l_object.cpp:385), so the whole table has to come
        # back or the game's own damage groups are gone.
        #
        # ponytail: no add_velocity to cancel a fall in progress - immortal covers the
        # landing. Add it if somebody really needs to catch a falling player unharmed *and*
        # motionless; that costs a get_velocity round trip before the hold.
        self._ask(
            f"""
            -- minetest.serialize and not write_json: the same table of numbers goes back
            -- into set_armor_groups later, and serialize is what `invisible` next door
            -- already trusts with a props table.
            local meta = player:get_meta()
            if meta:get_string({self.lt.lua.dumps(self._HOLD_KEY)}) == "" then
                meta:set_string({self.lt.lua.dumps(self._HOLD_KEY)}, minetest.serialize({{
                    gravity = player:get_physics_override().gravity,
                    armor_groups = player:get_armor_groups()
                }}) or "")
            end

            player:set_physics_override({{gravity = 0}})
            player:set_armor_groups({{immortal = 1}})
            return true
            """
        )

    def release(self) -> None:
        """
        Give this player their physics and their mortality back.

        **Put the player somewhere solid first.** Releasing them in mid-air is a fall from
        wherever they happen to be, which is the thing :meth:`hold` was there to prevent:

        .. code-block:: python

            import miney
            from miney import Point

            lt = miney.Luanti()
            player = lt.players["Steve"]

            player.hold()
            player.move(destination=Point(200, 80, 200), smooth=True, duration=5, wait=True)

            player.move(destination=Point(200, 12, 200))    # ground, then
            player.release()                               # physics

        What comes back is what the player had before :meth:`hold`, read from the record
        that :meth:`hold` wrote into their metadata - so a script that set
        ``player.gravity = 0.5`` gets ``0.5`` back and not ``1``. For a player this Miney
        never held, Luanti's own defaults are used, and calling it twice is harmless.

        .. note::
            On a server with damage switched off, Luanti keeps every player immortal and
            refuses to change it back. The player stays unhurtable after this call - which
            is what they were before it too, so nothing is lost.

        :return: None
        :raises ~miney.exceptions.PlayerOffline: if the player is not in the game.
        """
        self._ask(
            f"""
            local meta = player:get_meta()
            local saved = meta:get_string({self.lt.lua.dumps(self._HOLD_KEY)})
            local gravity, groups = 1, {{fleshy = 100}}
            if saved ~= "" then
                -- deserialize answers nil for anything it cannot read, which is the whole
                -- error handling this needs; the sandbox has no pcall.
                local before = minetest.deserialize(saved)
                if type(before) == "table" then
                    gravity = before.gravity or gravity
                    groups = before.armor_groups or groups
                end
                meta:set_string({self.lt.lua.dumps(self._HOLD_KEY)}, "")
            end

            player:set_physics_override({{gravity = gravity}})
            player:set_armor_groups(groups)
            return true
            """
        )

    #: How far :attr:`looking_at` follows the player's gaze, in nodes. Ten is well past
    #: the four Luanti lets a player reach, so it answers for things across a room rather
    #: than only what they could touch. Assign to it for a longer or shorter reach.
    look_range = 10

    @property
    def looking_at(self) -> Optional['Node']:
        """
        The block this player has their crosshair on, or ``None`` for open sky.

        *"Put something where I am looking"* is a whole program, and this is the half
        that was missing:

        .. code-block:: python

            import miney
            from miney import Node

            lt = miney.Luanti()
            player = lt.players["Steve"]

            target = player.looking_at
            if target:
                print("You are looking at", target.name)
                # one block on top of it
                lt.nodes.set(Node(target.x, target.y + 1, target.z,
                                  lt.nodes.names.default.torch))

        You get a :class:`~miney.node.Node`, so it carries where it is as well as what it is -
        ``target.x``, ``target.name`` - and it can go straight into anything that takes a
        position.

        The line stops after :attr:`look_range` nodes, ten by default. Water counts as
        something to look at, air does not.

        :return: The :class:`~miney.node.Node` in the crosshair, or ``None`` if there is
                 nothing within reach.
        :raises ~miney.exceptions.PlayerOffline: If the player is not in the game.
        """
        from .node import Node

        # From the eyes, not from the feet: get_pos() is where the player stands, and a
        # ray from there aims about 1.6 nodes below the crosshair - close enough to look
        # right and wrong enough to point at the floor when the player looks level.
        # eye_height is a property because a game may change it (sitting, a mount).
        seen = self._ask(
            f"""
            local props = player:get_properties()
            local eye = vector.add(player:get_pos(),
                {{x = 0, y = props.eye_height or 1.625, z = 0}})
            local far = vector.add(eye,
                vector.multiply(player:get_look_dir(), {self.look_range}))

            -- objects = false: this answers with a node. liquids = true, because a
            -- player looking at a lake and being told "nothing there" is a bug to them.
            for pointed in minetest.raycast(eye, far, false, true) do
                if pointed.type == "node" then
                    local node = minetest.get_node(pointed.under)
                    return {{x = pointed.under.x, y = pointed.under.y,
                             z = pointed.under.z, name = node.name,
                             param1 = node.param1, param2 = node.param2}}
                end
            end
            return nil
            """
        )
        if not seen:
            return None
        return Node(
            seen["x"], seen["y"], seen["z"],
            name=seen["name"],
            param1=seen.get("param1"),
            param2=seen.get("param2"),
            luanti=self.lt,
        )

    @property
    def wielding(self) -> str:
        """
        What this player is holding, as the item's name.

        Together with :attr:`looking_at` this is the first interactive program somebody
        writes - the game asks what you are doing, and Python decides what happens:

        .. code-block:: python

            if player.wielding == lt.items.default.torch and player.looking_at:
                lt.chat.send_to_player(player.name, "Light it up!")

        A hand can hold a block, a tool or anything else the game has, so
        :attr:`lt.items <miney.Luanti.items>` is the list to compare against - it is the
        only one that covers all three, and TAB finds the name for you.

        An empty hand is an empty string, so ``if player.wielding:`` asks whether they
        are holding anything at all.

        Read-only on purpose. Luanti has no way to *give* somebody an item in their hand -
        writing there replaces the whole stack, so putting a pickaxe into a hand holding
        64 blocks of dirt would delete the dirt. Use
        :meth:`player.inventory.add() <miney.Inventory.add>` to give something out; it
        goes into the first free slot and takes nothing away.

        :return: The item name, for example ``'default:pick_mese'``, or ``''`` for an
                 empty hand.
        :raises ~miney.exceptions.PlayerOffline: If the player is not in the game.
        """
        return self._ask("return player:get_wielded_item():get_name()")

    @property
    def keys(self) -> dict:
        """
        Which keys this player is holding down right now, as a dictionary of yes and no.

        A program that reacts to the game without callbacks, decorators or events - a
        ``while`` loop and an ``if`` is enough:

        .. code-block:: python

            import time

            while True:
                if player.keys["jump"]:
                    lt.chat.send_to_all(f"{player.name} jumped!")
                time.sleep(0.5)

        The names are Luanti's: ``up``, ``down``, ``left``, ``right``, ``jump``,
        ``sneak``, ``dig``, ``place``, ``aux1`` (the "special" key) and ``zoom``.
        ``dig`` is the left mouse button and ``place`` the right one.

        .. note::
            This is a question asked of the server, so it costs a round trip - around
            30 ms. Reading it in a tight loop asks hundreds of times a second and gets
            nearly the same answer every time; a small :func:`time.sleep` in the loop
            leaves the server room to breathe. :meth:`lt.callbacks.on()
            <miney.callback.Callback.on>` is the other way round for anything that must not be
            missed.

        :return: Every key, with ``True`` while it is held down.
        :raises ~miney.exceptions.PlayerOffline: If the player is not in the game.
        """
        control = self._ask("return player:get_player_control()") or {}
        # Only the yes-or-no fields. LMB and RMB are the old names of dig and place and
        # are documented as being there for compatibility, so they would be the same
        # answer twice under a name nobody should learn. Newer servers also put
        # movement_x and movement_y in here, which are floats and do not exist on the
        # 5.9 Miney still supports - reachable through lt.lua.run() for whoever needs
        # them, and out of a dictionary that promises True or False.
        return {key: value for key, value in control.items()
                if isinstance(value, bool) and key not in ("LMB", "RMB")}

    @property
    def velocity(self) -> Vector:
        """
        How fast this player is moving, and in which direction, in nodes per second.

        Standing still is a vector of zeros; falling is a negative ``y``.

        .. code-block:: python

            if player.velocity.y < -10:
                lt.chat.send_to_player(player.name, "That is a long way down.")

        Read-only, because Luanti has no way to set a player's speed outright.
        :meth:`push` adds to it, which is what a launchpad or a gust of wind does.

        :return: A :class:`~miney.vector.Vector` of nodes per second.
        :raises ~miney.exceptions.PlayerOffline: If the player is not in the game.
        """
        return Vector(**self._ask("return player:get_velocity()"))

    def push(self, force: Vector) -> None:
        """
        Give this player a shove.

        The force is added to how they are already moving, in nodes per second, so
        ``Vector(0, 6.5, 0)`` is about the same as them pressing the jump key:

        .. code-block:: python

            import miney
            from miney import Vector

            lt = miney.Luanti()
            player = lt.players["Steve"]

            player.push(Vector(0, 20, 0))       # straight up, and quite far
            player.push(player.look_dir * 15)   # forwards, wherever they are looking

        .. note::
            Luanti evens out a player's speed on every step, so a large push in one
            direction eats away at the speed they had in the others, and the number you
            give is not the number you get. Push, look at what happens, push harder -
            that is the honest way to use it, and it is a fine thing to let a beginner
            experiment with.

            It does nothing at all while the player is flying (:attr:`fly` with the
            client in free-move), and a held player (:meth:`hold`) keeps whatever push
            they were given, because nothing slows them down again.

        :param force: A :class:`~miney.vector.Vector` of nodes per second to add.
        :return: None
        :raises TypeError: If ``force`` is not a :class:`~miney.vector.Vector`.
        :raises ~miney.exceptions.PlayerOffline: If the player is not in the game.
        """
        if not isinstance(force, Vector):
            raise TypeError(
                f"push() takes a Vector, not {type(force).__name__} - a direction with a "
                f"length, like Vector(0, 20, 0) for straight up. A Point is a place, not "
                f"a push."
            )
        self._ask(f"player:add_velocity({self.lt.lua.dumps(force)}) return true")

    @property
    def size(self) -> float:
        """
        How big this player looks, as a multiple of normal. ``1`` is normal size.

        .. code-block:: python

            player.size = 3      # a giant
            player.size = 0.3    # small enough to lose
            player.size = 1      # back to normal

        .. important::
            Only the picture changes. The player still takes up exactly one player's
            worth of room, so a giant fits through a normal door and a tiny player does
            not fit under a slab. Luanti draws the model and moves the body separately,
            and this is the drawing.

        :return: The current size, ``1`` being normal.
        :raises TypeError: If the value is not a number.
        :raises ValueError: If the value is not above zero.
        :raises ~miney.exceptions.PlayerOffline: If the player is not in the game.
        """
        return self._ask("return player:get_properties().visual_size.x")

    @size.setter
    def size(self, value: float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(
                f"Size is a number, not {type(value).__name__}. Use 1 for normal size, "
                f"2 for twice as big, 0.5 for half."
            )
        if value <= 0:
            raise ValueError(
                f"Size has to be above 0, not {value}. Use a small number like 0.1 for "
                f"tiny; a size of 0 makes the player invisible instead - that is "
                f"player.invisible = True."
            )
        # All three axes together, so the player stays in proportion. z only shows on the
        # cube and sprite visuals, but setting it costs nothing and leaving it out would
        # squash a player in a game that uses one.
        self._ask(
            f"player:set_properties({{visual_size = "
            f"{{x = {value}, y = {value}, z = {value}}}}}) return true"
        )

    def respawn(self) -> None:
        """
        Send this player back to where they would appear after dying.

        The same thing the *Respawn* button does, including everything the game does
        about it. Their health, their inventory and everything else stay as they are -
        this moves them, it does not kill them.

        .. code-block:: python

            player.respawn()

        Useful for getting somebody out of a hole they dug themselves into, and as the
        way home from a script that flew them somewhere:

        .. code-block:: python

            player.hold()
            player.move(destination=Point(2000, 100, 2000), smooth=True, duration=10,
                        wait=True)
            player.release()
            player.respawn()

        :return: None
        :raises ~miney.exceptions.PlayerOffline: If the player is not in the game.
        """
        self._ask("player:respawn() return true")

    @property
    def armor_groups(self) -> dict:
        """
        What this player can be hurt by, and how much, as a dictionary.

        Luanti's own words for it are *armor groups*, and the useful one is
        ``fleshy``: it is a percentage, ``100`` being the normal amount of damage, ``50``
        half of it and ``0`` none::

            >>> player.armor_groups
            {'fleshy': 100}
            >>> player.armor_groups = {"fleshy": 50}    # half damage from everything

        ``{"immortal": 1}`` is the switch for *nothing hurts this player at all*, and it
        also stops them drowning. :meth:`hold` sets it for you and :meth:`release` puts
        back what was there before, which is the way to reach for it in a script.

        .. warning::
            Assigning replaces the whole dictionary, the way Luanti does it - the groups
            you leave out are gone, not left alone. Read it, change what you want and
            assign the result back::

                groups = player.armor_groups
                groups["fleshy"] = 20
                player.armor_groups = groups

        .. note::
            A server with damage switched off keeps every player immortal whatever is
            written here, and says so in its log.

        :return: The groups and their percentages.
        :raises TypeError: If the value is not a dictionary of names and whole numbers.
        :raises ~miney.exceptions.PlayerOffline: If the player is not in the game.
        """
        return self._ask("return player:get_armor_groups()") or {}

    @armor_groups.setter
    def armor_groups(self, value: dict):
        if not isinstance(value, dict):
            raise TypeError(
                f"Armor groups are a dictionary, not {type(value).__name__}. "
                f'For example {{"fleshy": 50}} for half damage.'
            )
        for name, percent in value.items():
            if not isinstance(name, str):
                raise TypeError(
                    f"An armor group is named with a string, not "
                    f'{type(name).__name__}. For example {{"fleshy": 50}}.'
                )
            if isinstance(percent, bool) or not isinstance(percent, int):
                raise TypeError(
                    f"An armor group is a whole number, not "
                    f'{type(percent).__name__}. {{"{name}": 100}} is the normal amount '
                    f"of damage, 50 is half."
                )
        self._ask(f"player:set_armor_groups({self.lt.lua.dumps(value)}) return true")

    @property
    def look(self) -> dict:
        """
        Get and set look in radians. Horizontal angle is counter-clockwise from the +z direction. Vertical angle ranges
        between -pi/2 (~-1.563) and pi/2 (~1.563), which are straight up and down respectively.

        :return: A dict like {'v': 0.34, 'h': 2.50} where h is horizontal and v = vertical
        """

        return self.lt.lua.run(
            f"return {{"
            f"h=minetest.get_player_by_name('{self.name}'):get_look_horizontal(), "
            f"v=minetest.get_player_by_name('{self.name}'):get_look_vertical()"
            f"}}"
        )

    @look.setter
    def look(self, value: dict):
        if type(value) is dict:
            if "v" in value and "h" in value:
                if type(value["v"]) in [int, float] and type(value["h"]) in [int, float]:
                    self.lt.lua.run(
                        f"""
                        local player = minetest.get_player_by_name('{self.name}')
                        player:set_look_horizontal({value["h"]})
                        player:set_look_vertical({value["v"]})
                        return true
                        """
                    )
                else:
                    raise TypeError("values for v or h aren't float or int")
            else:
                raise TypeError("There isn't the required v or h key in the dict")
        else:
            raise TypeError("The value isn't a dict, as required. Use a dict in the form: {\"h\": 1.1, \"v\": 1.1}")

    @property
    def look_dir(self) -> Vector:
        """
        Get or set the player's look direction as a normalized vector.

        :return: A :class:`~miney.vector.Vector` representing the look direction.
        """
        res = self.lt.lua.run(f"return minetest.get_player_by_name('{self.name}'):get_look_dir()")
        return Vector(**res)

    @look_dir.setter
    def look_dir(self, value: Vector):
        """
        Sets the player's look direction using a vector.

        Luanti has no ``set_look_dir`` to mirror its ``get_look_dir`` - a player is
        aimed with two angles, not with a vector - so the vector is converted to a yaw
        and a pitch here. Calling the method that does not exist is what this used to
        do, and it raised *attempt to call method 'set_look_dir' (a nil value)* for
        every value.
        """
        self.lt.lua.run(
            f"""
            local player = minetest.get_player_by_name({self.lt.lua.dumps(self.name)})
            if not player then return false end
            local rot = vector.dir_to_rotation({self.lt.lua.dumps(value)})
            player:set_look_horizontal(rot.y)
            -- Negated: dir_to_rotation counts pitch positive upwards,
            -- set_look_vertical counts it positive downwards.
            player:set_look_vertical(-rot.x)
            return true
            """
        )

    @property
    def look_vertical(self):
        """
        Get and set pitch in radians. Angle ranges between -pi/2 (~-1.563) and pi/2 (~1.563), which are straight
        up and down respectively.

        :return: Pitch in radians
        """
        return self.lt.lua.run("return minetest.get_player_by_name('{}'):get_look_vertical()".format(self.name))

    @look_vertical.setter
    def look_vertical(self, value):
        self.lt.lua.run("return minetest.get_player_by_name('{}'):set_look_vertical({})".format(self.name, value))

    @property
    def look_horizontal(self):
        """
        Get and set yaw in radians. Angle is counter-clockwise from the +z direction.

        :return: Pitch in radians
        """
        return self.lt.lua.run("return minetest.get_player_by_name('{}'):get_look_horizontal()".format(self.name))

    @look_horizontal.setter
    def look_horizontal(self, value):
        self.lt.lua.run("return minetest.get_player_by_name('{}'):set_look_horizontal({})".format(self.name, value))

    @property
    def hp(self):
        """
        Get and set the number of hitpoints (2 * number of hearts) between 0 and 20.
        By setting his hitpoint to zero you instantly kill this player.

        :return:
        """
        return self.lt.lua.run(f"return minetest.get_player_by_name('{self.name}'):get_hp()")

    @hp.setter
    def hp(self, value: int):
        if type(value) is int and value in range(0, 21):
            self.lt.lua.run(
                f"minetest.get_player_by_name('{self.name}'):set_hp({value}, {{type=\"set_hp\"}})",
                wait=False)
        else:
            raise ValueError("HP has to be between 0 and 20.")

    @property
    def privileges(self) -> 'PrivilegeManager':
        """
        Get, set, or modify player privileges using a list-like interface.

        This property provides an intuitive way to manage permissions
        on the server. It returns a special ``PrivilegeManager`` object that
        behaves like a list of strings.

        **Examples:**

        .. code-block:: python

            # Get a player object
            player = lt.player["some_player"]

            # 1. List all privileges
            # Returns a list of strings, e.g., ['interact', 'shout']
            current_privs = player.privileges.list()
            print(f"Current privileges: {current_privs}")

            # You can also iterate over it directly
            for priv in player.privileges:
                print(f"Player has privilege: {priv}")

            # 2. Check for a specific privilege
            if "fly" in player.privileges:
                print("Player can fly!")
            else:
                print("Player cannot fly.")

            # 3. Grant (append) a new privilege
            # This sends a command to the server to add 'fly'.
            player.privileges.append("fly")
            assert "fly" in player.privileges

            # 4. Revoke (remove) a privilege
            # This sends a command to the server to remove 'fly'.
            player.privileges.remove("fly")
            assert "fly" not in player.privileges

            # 5. Overwrite all privileges
            # This replaces all existing privileges with the new list.
            player.privileges = ["interact", "fast", "noclip"]
            assert player.privileges.list() == ["interact", "fast", "noclip"]

        :return: A :class:`~miney.player.PrivilegeManager` instance.
        """
        return PrivilegeManager(self)

    @privileges.setter
    def privileges(self, privileges: Iterable[str]):
        """
        Set all privileges for the player, overwriting any existing ones.

        :param privileges: An iterable of strings representing the desired privileges.
        """
        if not isinstance(privileges, Iterable) or isinstance(privileges, str):
            raise TypeError("Privileges must be an iterable of strings (e.g., a list or tuple).")

        priv_table = {priv: True for priv in privileges}
        self.lt.lua.run(
            f"""
            minetest.set_player_privs("{self.name}", {self.lt.lua.dumps(priv_table)})
            """,
            wait=False,
        )

    @property
    def breath(self):
        return self.lt.lua.run(f"return minetest.get_player_by_name('{self.name}'):get_breath()")

    @breath.setter
    def breath(self, value: int):
        if type(value) is int and value in range(0, 21):
            self.lt.lua.run(
                f"minetest.get_player_by_name('{self.name}'):set_breath({value}, {{type=\"set_hp\"}})",
                wait=False)
        else:
            raise ValueError("HP has to be between 0 and 20.")

    @property
    def fly(self) -> bool:
        """
        Get and set the 'fly' privilege. The player can fly by pressing the K key.
        """
        return "fly" in self.privileges

    @fly.setter
    def fly(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError("Value for 'fly' must be a boolean.")
        if value:
            if "fly" not in self.privileges:
                self.privileges.append("fly")
        else:
            if "fly" in self.privileges:
                self.privileges.remove("fly")

    @property
    def fast(self) -> bool:
        """
        Get and set the 'fast' privilege.
        """
        return "fast" in self.privileges

    @fast.setter
    def fast(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError("Value for 'fast' must be a boolean.")
        if value:
            if "fast" not in self.privileges:
                self.privileges.append("fast")
        else:
            if "fast" in self.privileges:
                self.privileges.remove("fast")

    @property
    def noclip(self) -> bool:
        """
        Get and set the 'noclip' privilege.
        """
        return "noclip" in self.privileges

    @noclip.setter
    def noclip(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError("Value for 'noclip' must be a boolean.")
        if value:
            if "noclip" not in self.privileges:
                self.privileges.append("noclip")
        else:
            if "noclip" in self.privileges:
                self.privileges.remove("noclip")

    @property
    def invisible(self) -> bool:
        """
        Get or set the player's visibility.

        When set to ``True``, the player model, nametag and minimap marker are hidden,
        and nothing can point at them any more - no hitbox, no selection box.

        Setting it back to ``False`` puts back what the player looked like before,
        including the skin this game gave them. That is remembered in the player's
        metadata rather than guessed, so it survives a script that ends while its player
        is hidden.

        .. code-block:: python

            ghost = lt.players["Steve"]
            ghost.invisible = True      # out of the way, and out of reach
            ghost.invisible = False     # back, with the same skin as before

        .. note::
            This feature may not work for mobs in some games, so they may still attack the player. Maybe it's better to
            move the player to a safe spot.

        :return: ``True`` if the player is currently invisible, ``False`` otherwise.
        """
        return self.lt.lua.run(
            f"""
            local player = minetest.get_player_by_name('{self.name}')
            if not player then
                return false -- Player is not online, so not invisible
            end
            local props = player:get_properties()
            -- 'pointable' is false when invisible. We return true if invisible.
            return not props.pointable
            """
        )

    @invisible.setter
    def invisible(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError("Value for invisible must be a boolean (True or False).")

        if value:
            # What the player looked like is written down before it is taken away, so
            # that turning this off puts back what this game gave them - a skin, a model,
            # a size - instead of a guess. It goes into the player's own metadata, which
            # survives a disconnect: a script that dies while its player is invisible
            # leaves a way back rather than a permanently blank character.
            self.lt.lua.run(
                f"""
                local player = minetest.get_player_by_name('{self.name}')
                if not player then return end

                -- minetest.serialize and not write_json: a player's selectionbox is a
                -- list of numbers *and* a 'rotate' flag in one table, and write_json
                -- refuses to mix the two - it answers nil, and the appearance would be
                -- lost with nothing said about it.
                local meta = player:get_meta()
                if meta:get_string("miney:before_invisible") == "" then
                    local props = player:get_properties()
                    meta:set_string("miney:before_invisible", minetest.serialize({{
                        visual = props.visual,
                        mesh = props.mesh,
                        textures = props.textures,
                        visual_size = props.visual_size,
                        pointable = props.pointable,
                        makes_footstep_sound = props.makes_footstep_sound,
                        collisionbox = props.collisionbox,
                        selectionbox = props.selectionbox,
                        show_on_minimap = props.show_on_minimap
                    }}) or "")
                end

                player:set_properties({{
                    visual = "cube",
                    textures = {{"blank.png"}},
                    visual_size = {{x = 0, y = 0}},
                    pointable = false,
                    makes_footstep_sound = false,
                    collisionbox = {{0,0,0, 0,0,0}},
                    selectionbox = {{0,0,0, 0,0,0}},
                    show_on_minimap = false
                }})

                player:set_nametag_attributes({{
                    color = {{a = 0, r = 255, g = 255, b = 255}}
                }})
                """
            )
        else:
            # Make player visible again, from what was written down when they were
            # hidden. The fallback is only for a player this Miney never hid: it is a
            # plain character, which is right in most games and at least visible in all
            # of them.
            self.lt.lua.run(
                f"""
                local player = minetest.get_player_by_name('{self.name}')
                if not player then return end

                local meta = player:get_meta()
                local saved = meta:get_string("miney:before_invisible")
                local restored = false
                if saved ~= "" then
                    -- deserialize answers nil for anything it cannot read, which is the
                    -- whole error handling this needs; the sandbox has no pcall.
                    local props = minetest.deserialize(saved)
                    if type(props) == "table" then
                        player:set_properties(props)
                        restored = true
                    end
                    meta:set_string("miney:before_invisible", "")
                end

                if not restored then
                    player:set_properties({{
                        visual = "mesh",
                        textures = {{"character.png"}},
                        visual_size = {{x = 1, y = 1}},
                        pointable = true,
                        makes_footstep_sound = true,
                        collisionbox = {{-0.3, -1.0, -0.3, 0.3, 1.0, 0.3}},
                        selectionbox = {{-0.3, -1.0, -0.3, 0.3, 1.0, 0.3}},
                        show_on_minimap = true
                    }})
                end

                player:set_nametag_attributes({{
                    color = {{a = 255, r = 255, g = 255, b = 255}}
                }})
                """
            )

    @property
    def creative(self) -> bool:
        """
        Get and set the player's creative mode.

        .. note::
            The implementation of this property is game-dependent. For games
            like **VoxeLibre (mineclone2)**, it uses the native ``mcl_gamemode``
            system. For other games, it falls back to granting or revoking the
            ``creative`` privilege.

        :return: ``True`` if the player is in creative mode, ``False`` otherwise.
        """
        if self.lt.game_info.id in ['mineclone2']:
            gamemode = self.lt.lua.run(
                f"""
                local player = minetest.get_player_by_name('{self.name}')
                if player then
                    return player:get_meta():get_string("gamemode")
                end
                return "survival"
                """
            )
            return gamemode == 'creative'
        else:
            return "creative" in self.privileges

    @creative.setter
    def creative(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError("Value for 'creative' must be a boolean.")

        if self.lt.game_info.id in ['mineclone2']:
            gamemode = "creative" if value else "survival"
            self.lt.lua.run(
                f"""
                if mcl_gamemode and mcl_gamemode.set_gamemode then
                    local player = minetest.get_player_by_name('{self.name}')
                    if player then
                        mcl_gamemode.set_gamemode(player, '{gamemode}')
                    end
                end
                """
            )
        else:
            # Fallback for other games: use the 'creative' privilege
            if value:
                if "creative" not in self.privileges:
                    self.privileges.append("creative")
            else:
                if "creative" in self.privileges:
                    self.privileges.remove("creative")


class PlayerIterable:
    """Player, implemented as iterable for easy autocomplete in the interactive shell"""
    def __init__(self, luanti: 'Luanti', online_players: list = None):
        # Set even when nobody is online, which used to be impossible and is now the
        # normal case: Miney reaches a world on this computer through its files and
        # does not join it, so an empty world really is empty. Guarding the assignment
        # left the attributes missing entirely, and `list(lt.players)` answered with
        # AttributeError instead of an empty list.
        self.__online_players = list(online_players or [])
        self.__mt = luanti

        for player in self.__online_players:
            self.__setattr__(player, Player(luanti, player))

    def __iter__(self):
        player_object = []
        for player in self.__online_players:
            player_object.append(Player(self.__mt, player))

        return iter(player_object)

    def __getitem__(self, item_key) -> Player:
        if item_key in self.__online_players:
            return self.__getattribute__(item_key)
        else:
            if type(item_key) == int:
                return self.__getattribute__(self.__online_players[item_key])
            online = ", ".join(repr(name) for name in self.__online_players)
            who = f"Online: {online}." if online else "Nobody is online."
            raise PlayerNotFoundError(f"There is no player {item_key!r}. {who}")

    def __len__(self):
        return len(self.__online_players)

    def __repr__(self):
        return f"<Players: {self.__online_players}>"
