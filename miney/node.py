import miney
from typing import Dict, List, Union


class Node:
    """
    Manipulate and get information's about nodes.
    """
    def __init__(self, mt: miney.Minetest):
        self.mt = mt

        self._types_cache = self.mt.lua.run(
            """
            local nodes = {}
            for name, def in pairs(minetest.registered_nodes) do
                table.insert(nodes, name)
            end return nodes
            """
        )
        self._types = TypeIterable(self, self._types_cache)

    @property
    def type(self) -> 'TypeIterable':
        """
        All available node types in the game, sorted by categories. In the end it just returns the corresponding
        minetest type string, so `mt.node.types.default.dirt` returns the string 'default:dirt'.
        It's a nice shortcut in REPL, cause with auto completion you have only pressed 2-4 keys to get to your type.

        :Examples:

            Directly access a type:

            >>> mt.node.type.default.dirt
            'default:dirt'

            Iterate over all available types:

            >>> for node_type in mt.node.type:
            >>>     print(node_type)
            default:pine_tree
            default:dry_grass_5
            farming:desert_sand_soil
            ... (there should be over 400 different types)
            >>> print(len(mt.node.type))
            421

            Get a list of all types:

            >>> list(mt.node.type)
            ['default:pine_tree', 'default:dry_grass_5', 'farming:desert_sand_soil', ...

            Add 99 dirt to player "IloveDirt"'s inventory:

            >>> mt.player.IloveDirt.inventory.add(mt.node.type.default.dirt, 99)

        :rtype: :class:`TypeIterable`
        :return: :class:`TypeIterable` object with categories. Look at the examples above for usage.
        """
        return self._types

    def set(self, position: Union[dict, list], offset: dict = None, node_type: str = "air") -> None:
        """
        Set a single or multiple nodes at given position to another node type
        (something like mt.node.type.default.apple).
        You can get a list of all available nodes with :attr:`~miney.Minetest.node.type`

        :Examples:

            Set a single node over :

            >>> pos = mt.player[0].position
            >>> mt.node.set({pos[])

        :param position: a dict with x,y,z keys
        :param offset:
        :param node_type: a valid node name like default:dirt as string or via :attr:`~miney.Minetest.node.type`
        """
        if offset and not all(name in ['x', 'y', 'z'] for name in offset):
            raise ValueError("offset parameter dict needs y, x and z keys")
        if type(position) is dict:  # a single node
            if offset:
                position["x"] = position["x"] + offset["x"]
                position["y"] = position["y"] + offset["y"]
                position["z"] = position["z"] + offset["z"]
            if "name" in position:  # name = node_type in minetest
                node_type = position["name"]
            self.mt.lua.run(f"minetest.set_node({self.mt.lua.dumps(position)}, {{name=\"{node_type}\"}})")
        elif type(position) is list:  # bulk
            if offset:
                new_positions = []
                for pos in position:
                    new_pos = {"x": pos["x"] + offset["x"], "y": pos["y"] + offset["y"], "z": pos["z"] + offset["z"]}
                    if "name" in pos:
                        new_pos["name"] = pos["name"]
                    new_positions.append(new_pos)
                position = new_positions
            if 'name' not in position[0]:  # we have a list where all nodes get the same node type
                chunk_size = 700  # limit from trial&error
                for x in range(0, len(position), chunk_size):
                    self.mt.lua.run(
                        f"minetest.bulk_set_node({self.mt.lua.dumps(position[x:x+chunk_size])}, "
                        f"{{name=\"{node_type}\"}})")
            if "name" in position[0]:  # mixed node type, so we can't use bulk_set_node
                lua = ""
                for pos in position:
                    # print("pos", pos)
                    if pos["name"] != "ignore":
                        lua = lua + f"minetest.set_node(" \
                                    f"{self.mt.lua.dumps({'x': pos['x'], 'y': pos['y'], 'z': pos['z']})}, " \
                                    f"{{name=\"{pos['name']}\"}})\n"
                self.mt.lua.run(lua)

    def get(self, position: dict, position2: dict = None) -> str:
        """
        Get the node type at given position (something like "default:wood").
        If also position2 is given, this function returns a cuboid with the diagonal between position and position2.
        You can get a list of all available node type with :attr:`~miney.Minetest.node.type`.

        :param position: A dict with x,y,z keys
        :param position2: Another point, if you want an area
        :return: The node type on this position
        """
        if type(position) is dict and not position2:  # for a single node
            return self.mt.lua.run(f"return minetest.get_node({self.mt.lua.dumps(position)})")
        elif type(position2) is dict:  # Multiple nodes
            return self.mt.lua.run(f"""
                pos1 = {self.mt.lua.dumps(position)}
                pos2 = {self.mt.lua.dumps(position2)}
                nodes = {{}}
                if pos1.x <= pos2.x then start_x = pos1.x end_x = pos2.x else start_x = pos2.x end_x = pos1.x end
                if pos1.y <= pos2.y then start_y = pos1.y end_y = pos2.y else start_y = pos2.y end_y = pos1.y end
                if pos1.z <= pos2.z then start_z = pos1.z end_z = pos2.z else start_z = pos2.z end_z = pos1.z end
                
                for x = start_x, end_x do
                  for y = start_y, end_y do
                    for z = start_z, end_z do
                      node = minetest.get_node({{x = x, y = y, z = z}})
                      node["x"] = x - start_x
                      node["y"] = y - start_y
                      node["z"] = z - start_z
                      nodes[#nodes+1] = node  -- append node
                    end
                  end
                end
                return nodes""", timeout=180)

    def __repr__(self):
        return '<minetest node functions>'


class TypeIterable:
    """Node type, implemented as iterable for easy autocomplete in the interactive shell"""
    def __init__(self, parent, nodes_types=None):

        self.__parent = parent

        if nodes_types:

            # get type categories list
            type_categories = {}
            for ntype in nodes_types:
                if ":" in ntype:
                    type_categories[ntype.split(":")[0]] = ntype.split(":")[0]
            for tc in dict.fromkeys(type_categories):
                self.__setattr__(tc, TypeIterable(parent))

            # values to categories
            for ntype in nodes_types:
                if ":" in ntype:
                    self.__getattribute__(ntype.split(":")[0]).__setattr__(ntype.split(":")[1], ntype)
                else:
                    self.__setattr__(ntype, ntype)  # for 'air' and 'ignore'

    def __iter__(self):
        # todo: list(mt.node.type.default) should return only default group
        return iter(self.__parent._types_cache)

    def __getitem__(self, item_key):
        if item_key in self.__parent.node_types:
            return item_key
        else:
            if type(item_key) == int:
                return self.__parent.node_types[item_key]
            raise IndexError("unknown node type")

    def __len__(self):
        return len(self.__parent._types_cache)
