from typing import Union, Iterable, List, TYPE_CHECKING
from .exceptions import PlayerNotFoundError, PlayerOffline, LuaError
from .point import Point
if TYPE_CHECKING:
    from .luanti import Luanti


class PrivilegeManager:
    """
    Manages player privileges by providing a list-like interface.

    This object is returned by the :attr:`~miney.player.Player.privileges`
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
            raise PlayerNotFoundError("There is no player with that name")

        self.inventory: Inventory = Inventory(luanti, self)
        """Manipulate player's inventory.
        
        :Example to add 99 dirt to player "IloveDirt"'s inventory:
        
        >>> import miney
        >>> lt = miney.Luanti()
        >>> lt.player.IloveDirt.inventory.add(lt.nodes.names.default.dirt, 99)      
            
        :Example to remove 99 dirt from player "IhateDirt"'s inventory:
        
        >>> import miney
        >>> lt = miney.Luanti()
        >>> lt.player.IhateDirt.inventory.remove(lt.nodes.names.default.dirt, 99)
        """

    def __repr__(self):
        return '<Luanti Player "{}">'.format(self.name)

    @property
    def is_online(self) -> bool | None:
        """
        Returns the online status of this player.

        :return: True or False
        """
        return self.name in self.lt.luanti.state._connected_players

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
            """
        )

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
        Get and set the 'fly' privilege.
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
        """
        Get and set the 'creative' privilege.
        """
        return "creative" in self.privileges

    @creative.setter
    def creative(self, value: bool):
        if not isinstance(value, bool):
            raise TypeError("Value for 'creative' must be a boolean.")
        if value:
            if "creative" not in self.privileges:
                self.privileges.append("creative")
        else:
            if "creative" in self.privileges:
                self.privileges.remove("creative")


class PlayerIterable:
    """Player, implemented as iterable for easy autocomplete in the interactive shell"""
    def __init__(self, luanti: 'Luanti', online_players: list = None):
        if online_players:
            self.__online_players = online_players
            self.__mt = luanti

            # update list
            for player in online_players:
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
            raise IndexError("unknown player")

    def __len__(self):
        return len(self.__online_players)
