import time
from typing import Iterable, List, TYPE_CHECKING, Optional
from .exceptions import PlayerNotFoundError, PlayerOffline, LuaError
from .point import Point
from .vector import Vector
if TYPE_CHECKING:
    from .luanti import Luanti


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
