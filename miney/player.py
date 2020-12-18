from typing import Union
import miney

# todo: set modes creative/survival -> Not possible without installed minetest mods


class Player:
    """
    A player of the minetest server.
    """
    def __init__(self, minetest: miney.Minetest, name):
        """
        Initialize the player object.

        :param minetest: Parent minetest object
        :param name: Player name
        """
        self.mt = minetest
        self.name = name
        
        # get user data: password hash, last login, privileges
        data = self.mt.lua.run("return minetest.get_auth_handler().get_auth('{}')".format(self.name))
        if data and all(k in data for k in ("password", "last_login", "privileges")):  # if we have all keys
            self.password = data["password"]
            self.last_login = data["last_login"]
            self.privileges = data["privileges"]
        else:
            raise miney.PlayerInvalid("There is no player with that name")

        self.inventory: miney.Inventory = miney.Inventory(minetest, self)
        """Manipulate player's inventory.
        
        :Example to add 99 dirt to player "IloveDirt"'s inventory:
        
            >>> import miney
            >>> mt = miney.Minetest()
            >>> mt.player.IloveDirt.inventory.add(mt.node.type.default.dirt, 99)      
            
        :Example to remove 99 dirt from player "IhateDirt"'s inventory:
        
            >>> import miney
            >>> mt = miney.Minetest()
            >>> mt.player.IhateDirt.inventory.remove(mt.node.type.default.dirt, 99)
            
        """

    def __repr__(self):
        return '<minetest player "{}">'.format(self.name)

    @property
    def is_online(self) -> bool:
        """
        Returns the online status of this player.

        :return: True or False
        """
        # TODO: Better check without provoke a lua error
        try:
            if self.name == self.mt.lua.run(
                    "return minetest.get_player_by_name('{}'):get_player_name()".format(self.name)):
                return True
        except miney.LuaError:
            return False

    @property
    def position(self) -> dict:
        """
        Get the players current position.

        :return: A dict with x,y,z keys: {"x": 0, "y":1, "z":2}
        """
        try:
            return self.mt.lua.run("return minetest.get_player_by_name('{}'):get_pos()".format(self.name))
        except miney.LuaError:
            raise miney.PlayerOffline("The player has no position, he could be offline")

    @position.setter
    def position(self, values: dict):
        """
        Set player position
        :param values:
        :return:
        """
        if all(k in values for k in ("x", "y", "z")):  # if we have all keys
            self.mt.lua.run(
                "return minetest.get_player_by_name('{}'):set_pos({{x = {}, y = {}, z = {}}})".format(
                    self.name,
                    values["x"],
                    values["y"],
                    values["z"],
                )
            )
        else:
            raise miney.NoValidPosition(
                "A valid position need x,y,z values in an dict ({\"x\": 12, \"y\": 70, \"z\": 12}).")

    @property
    def speed(self) -> int:
        """
        Get or set the players speed. Default is 1.

        :return: Float
        """
        return self.mt.lua.run(
            "return minetest.get_player_by_name('{}'):get_physics_override()".format(self.name))["speed"]

    @speed.setter
    def speed(self, value: int):
        self.mt.lua.run(
            "return minetest.get_player_by_name('{}'):set_physics_override({{speed = {}}})".format(self.name, value))

    @property
    def jump(self):
        """
        Get or set the players jump height. Default is 1.

        :return: Float
        """
        return self.mt.lua.run(
            "return minetest.get_player_by_name('{}'):get_physics_override()".format(self.name))["jump"]

    @jump.setter
    def jump(self, value):
        self.mt.lua.run(
            "return minetest.get_player_by_name('{}'):set_physics_override({{jump = {}}})".format(self.name, value))

    @property
    def gravity(self):
        """
        Get or set the players gravity. Default is 1.

        :return: Float
        """
        return self.mt.lua.run(
            "return minetest.get_player_by_name('{}'):get_physics_override()".format(self.name))["gravity"]

    @gravity.setter
    def gravity(self, value):
        self.mt.lua.run(
            "return minetest.get_player_by_name('{}'):set_physics_override({{gravity = {}}})".format(self.name, value))

    @property
    def look(self) -> dict:
        """
        Get and set look in radians. Horizontal angle is counter-clockwise from the +z direction. Vertical angle ranges
        between -pi/2 (~-1.563) and pi/2 (~1.563), which are straight up and down respectively.

        :return: A dict like {'v': 0.34, 'h': 2.50} where h is horizontal and v = vertical
        """

        return self.mt.lua.run(
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
                    self.mt.lua.run(
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
        return self.mt.lua.run("return minetest.get_player_by_name('{}'):get_look_vertical()".format(self.name))

    @look_vertical.setter
    def look_vertical(self, value):
        self.mt.lua.run("return minetest.get_player_by_name('{}'):set_look_vertical({})".format(self.name, value))

    @property
    def look_horizontal(self):
        """
        Get and set yaw in radians. Angle is counter-clockwise from the +z direction.

        :return: Pitch in radians
        """
        return self.mt.lua.run("return minetest.get_player_by_name('{}'):get_look_horizontal()".format(self.name))

    @look_horizontal.setter
    def look_horizontal(self, value):
        self.mt.lua.run("return minetest.get_player_by_name('{}'):set_look_horizontal({})".format(self.name, value))

    @property
    def hp(self):
        """
        Get and set the number of hitpoints (2 * number of hearts) between 0 and 20.
        By setting his hitpoint to zero you instantly kill this player.

        :return:
        """
        return self.mt.lua.run(f"return minetest.get_player_by_name('{self.name}'):get_hp()")

    @hp.setter
    def hp(self, value: int):
        if type(value) is int and value in range(0, 21):
            self.mt.lua.run(
                f"return minetest.get_player_by_name('{self.name}'):set_hp({value}, {{type=\"set_hp\"}})")
        else:
            raise ValueError("HP has to be between 0 and 20.")

    @property
    def breath(self):
        return self.mt.lua.run(f"return minetest.get_player_by_name('{self.name}'):get_breath()")

    @breath.setter
    def breath(self, value: int):
        if type(value) is int and value in range(0, 21):
            self.mt.lua.run(
                f"return minetest.get_player_by_name('{self.name}'):set_breath({value}, {{type=\"set_hp\"}})")
        else:
            raise ValueError("HP has to be between 0 and 20.")

    @property
    def fly(self) -> bool:
        """
        Get and set the privilege to fly to this player. Press K to enable and disable fly mode.
        As a shortcut you can set fly to a number instead if `True` to also changes the players speed to this number.

        .. Example:

            >>> mt.player.MineyPlayer.fly = True  # the can player fly
            >>> mt.player.MineyPlayer.fly = 5  # the can player fly 5 times faster

        :return:
        """
        return self.mt.lua.run(
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
    def fly(self, value: Union[bool, int]):
        if value:
            state = "true"
            if type(value) is int:
                if value > 0:
                    self.speed = value
        else:
            state = "false"
        self.mt.lua.run(
            f"""
            local privs = minetest.get_player_privs(\"{self.name}\")
            privs["fly"] = {state}
            minetest.set_player_privs(\"{self.name}\", privs)
            """
        )

    @property
    def creative(self) -> bool:
        return self.mt.lua.run(
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
        self.mt.lua.run(
            luastring
        )


class PlayerIterable:
    """Player, implemented as iterable for easy autocomplete in the interactive shell"""
    def __init__(self, minetest: miney.Minetest, online_players: list = None):
        if online_players:
            self.__online_players = online_players
            self.__mt = minetest

            # update list
            for player in online_players:
                self.__setattr__(player, miney.Player(minetest, player))

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