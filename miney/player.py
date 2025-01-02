from typing import Union
import miney


class Player:
    """
    A player of the Luanti server.
    """
    def __init__(self, luanti: miney.Luanti, name):
        """
        Initialize the player object.

        :param luanti: Parent Luanti object
        :param name: Player name
        """
        self.lt = luanti
        self.name = name
        
        # get user data: password hash, last login, privileges
        data = self.lt.lua.run("return minetest.get_auth_handler().get_auth('{}')".format(self.name))
        if data and all(k in data for k in ("password", "last_login", "privileges")):  # if we have all keys
            self.password = data["password"]
            self.last_login = data["last_login"]
            self.privileges = data["privileges"]
        else:
            raise miney.PlayerInvalid("There is no player with that name")

        self.inventory: miney.Inventory = miney.Inventory(luanti, self)
        """Manipulate player's inventory.
        
        :Example to add 99 dirt to player "IloveDirt"'s inventory:
        
        >>> import miney
        >>> lt = miney.Luanti()
        >>> lt.player.IloveDirt.inventory.add(lt.node.type.default.dirt, 99)      
            
        :Example to remove 99 dirt from player "IhateDirt"'s inventory:
        
        >>> import miney
        >>> lt = miney.Luanti()
        >>> lt.player.IhateDirt.inventory.remove(lt.node.type.default.dirt, 99)
            
        """

    def __repr__(self):
        return '<Luanti Player "{}">'.format(self.name)

    @property
    def is_online(self) -> bool | None:
        """
        Returns the online status of this player.

        :return: True or False
        """
        # TODO: Better check without provoke a lua error
        try:
            if self.name == self.lt.lua.run(
                    "return minetest.get_player_by_name('{}'):get_player_name()".format(self.name)):
                return True
        except miney.LuaError:
            return False

    @property
    def position(self) -> miney.Point:
        """
        Get or set the players current position.

        To place a player on top of a specific node, add 0.5 to the y value and his feet will touch this node.
        A player needs two blocks in the y axis (he's around 1,5 node tall), or he is stuck.

        :return: :class:`miney.Point`
        """
        try:
            return miney.Point(
                **self.lt.lua.run("return minetest.get_player_by_name('{}'):get_pos()".format(self.name))
            )
        except miney.LuaError:
            raise miney.PlayerOffline("The player has no position, he could be offline")

    @position.setter
    def position(self, values: miney.Point) -> None:
        """
        Set player position
        :param values:
        :return: None
        """
        self.lt.lua.run(
            "return minetest.get_player_by_name('{}'):set_pos({{x = {}, y = {}, z = {}}})".format(
                self.name,
                values.x,
                values.y,
                values.z
            )
        )

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
            "return minetest.get_player_by_name('{}'):set_physics_override({{speed = {}}})".format(self.name, value))

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
            "return minetest.get_player_by_name('{}'):set_physics_override({{jump = {}}})".format(self.name, value))

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
            "return minetest.get_player_by_name('{}'):set_physics_override({{gravity = {}}})".format(self.name, value))

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
                f"return minetest.get_player_by_name('{self.name}'):set_hp({value}, {{type=\"set_hp\"}})")
        else:
            raise ValueError("HP has to be between 0 and 20.")

    @property
    def breath(self):
        return self.lt.lua.run(f"return minetest.get_player_by_name('{self.name}'):get_breath()")

    @breath.setter
    def breath(self, value: int):
        if type(value) is int and value in range(0, 21):
            self.lt.lua.run(
                f"return minetest.get_player_by_name('{self.name}'):set_breath({value}, {{type=\"set_hp\"}})")
        else:
            raise ValueError("HP has to be between 0 and 20.")

    @property
    def fly(self) -> bool:
        """
        Get and set the privilege to fly to this player. Press K to enable and disable fly mode.

        .. Example:

            >>> lt.player.MineyPlayer.fly = True  # the can player fly

        :return:
        """
        return self.lt.lua.run(
            f"""
            local privs = minetest.get_player_privs(\"{self.name}\")
            if privs["fly"] then
                return true
            else
                return false
            end
            """
        )

    @fly.setter
    def fly(self, value: bool):
        if value:
            state = "true"
        else:
            state = "false"
        self.lt.lua.run(
            f"""
            local privs = minetest.get_player_privs(\"{self.name}\")
            privs["fly"] = {state}
            minetest.set_player_privs(\"{self.name}\", privs)
            """
        )

    @property
    def fast(self) -> bool:
        """
        Get and set the privilege for fast mode to this player. Press J to enable and disable fast mode.

        .. Example:

            >>> lt.player.MineyPlayer.fast = True  # the player is fast

        :return:
        """
        return self.lt.lua.run(
            f"""
            local privs = minetest.get_player_privs(\"{self.name}\")
            if privs["fast"] then
                return true
            else
                return false
            end
            """
        )

    @fast.setter
    def fast(self, value: bool):
        if value:
            state = "true"
        else:
            state = "false"
        self.lt.lua.run(
            f"""
            local privs = minetest.get_player_privs(\"{self.name}\")
            privs["fast"] = {state}
            minetest.set_player_privs(\"{self.name}\", privs)
            """
        )

    @property
    def noclip(self) -> bool:
        """
        Get and set the privilege for noclip mode to this player. Press H to enable and disable noclip mode.

        .. Example:

            >>> lt.player.MineyPlayer.noclip = True  # the player can go through walls

        :return:
        """
        return self.lt.lua.run(
            f"""
                local privs = minetest.get_player_privs(\"{self.name}\")
                if privs["noclip"] then
                    return true
                else
                    return false
                end
                """
        )

    @noclip.setter
    def noclip(self, value: bool):
        if value:
            state = "true"
        else:
            state = "false"
        self.lt.lua.run(
            f"""
                local privs = minetest.get_player_privs(\"{self.name}\")
                privs["noclip"] = {state}
                minetest.set_player_privs(\"{self.name}\", privs)
                """
        )

    @property
    def invisible(self) -> bool:
        """
        Get or set the player's visibility.

        When set to ``True``, the player model, nametag, and minimap marker
        are hidden. When ``False``, restores normal appearance.

        .. note::
            This feature works independently of any specific mod like 'invis'
            by directly manipulating player properties. The default player
            collision box is restored when made visible.

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
            # Make player invisible
            self.lt.lua.run(
                f"""
                local player = minetest.get_player_by_name('{self.name}')
                if not player then return end

                player:set_properties({{
                    visual = "sprite",
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
            # Make player visible
            self.lt.lua.run(
                f"""
                local player = minetest.get_player_by_name('{self.name}')
                if not player then return end

                player:set_properties({{
                    visual = "mesh",
                    visual_size = {{x = 1, y = 1}},
                    pointable = true,
                    makes_footstep_sound = true,
                    collisionbox = {{-0.3, -1.0, -0.3, 0.3, 1.0, 0.3}},
                    selectionbox = {{-0.3, -1.0, -0.3, 0.3, 1.0, 0.3}},
                    show_on_minimap = true
                }})

                player:set_nametag_attributes({{
                    color = {{a = 255, r = 255, g = 255, b = 255}}
                }})
                """
            )

    @property
    def creative(self) -> bool:
        return self.lt.lua.run(
            f"""
            local privs = minetest.get_player_privs(\"{self.name}\")
            if privs["creative"] then
                return true
            else
                return false
            end
            """
        )

    @creative.setter
    def creative(self, value: bool):
        if type(value) is not bool:
            raise ValueError("creative needs to be true or false")
        if value is True:
            state = "true"
        else:
            state = "false"

        luastring = f"""
            local privs = minetest.get_player_privs(\"{self.name}\")
            privs["creative"] = {state}
            minetest.set_player_privs(\"{self.name}\", privs)
            """
        self.lt.lua.run(
            luastring
        )


class PlayerIterable:
    """Player, implemented as iterable for easy autocomplete in the interactive shell"""
    def __init__(self, luanti: miney.Luanti, online_players: list = None):
        if online_players:
            self.__online_players = online_players
            self.__mt = luanti

            # update list
            for player in online_players:
                self.__setattr__(player, miney.Player(luanti, player))

    def __iter__(self):
        player_object = []
        for player in self.__online_players:
            player_object.append(miney.Player(self.__mt, player))

        return iter(player_object)

    def __getitem__(self, item_key) -> Player:
        if item_key in self.__online_players:
            return self.__getattribute__(item_key)
        else:
            if type(item_key) == int:
                return self.__getattribute__(self.__online_players[item_key])
            raise IndexError("unknown player")

    def __len__(self):
        return len(self.__online_players)
