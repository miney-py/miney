import miney
from typing import Union
from copy import deepcopy


class Node:
    """
    Manipulate and get information's about nodes.

    **Node manipulation is currently tested for up to 25.000 nodes, more optimization will come later**

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

    def set(self, nodes: Union[dict, list], name: str = None, offset: dict = None) -> None:
        """
        Set a single or multiple nodes at given position to another node type
        (something like mt.node.type.default.apple).
        You can get a list of all available nodes with :attr:`~miney.Minetest.node.type`

        A node is defined as a dict with these keys:
         * "x", "y", and "z" keys to define the absolute position
         * "name" for a the node type like "default:dirt" (you can also get that from mt.node.type.default.dirt).
           Dicts without name will be set as "air"
         * some other optional minetest parameters

        **The nodes parameter can be a single dict with the above parameters
        or a list of these dicts for bulk spawning.**

        :Examples:

            Set a single node over :

            >>> mt.node.set(mt.player[0].nodes, mt.node)

        :param nodes: A dict or a list of dicts with node definitions
        :param name: a type name like "default:dirt" as string or from :attr:`~miney.Minetest.node.type`. This overrides
        node names defined in the :attr:`nodes` dict
        :param offset: A dict with "x", "y", "z" keys. All node positions will be added with this values.
        """

        _nodes = deepcopy(nodes)

        if offset:
            if not all(pos in ['x', 'y', 'z'] for pos in offset):
                raise ValueError("offset parameter dict needs y, x and z keys")

        # Set a single node
        if type(_nodes) is dict:
            if offset:
                _nodes["x"] = _nodes["x"] + offset["x"]
                _nodes["y"] = _nodes["y"] + offset["y"]
                _nodes["z"] = _nodes["z"] + offset["z"]
            if name:
                _nodes["name"] = name
            self.mt.lua.run(f"minetest.set_node({self.mt.lua.dumps(_nodes)}, {{name=\"{_nodes['name']}\"}})")

        # Set many blocks
        elif type(_nodes) is list:

            lua = ""
            # Loop over nodes, modify name/type, position/offset and generate lua code
            for node in _nodes:
                # default name to 'air'
                if "name" not in node and not name:
                    node["name"] = "air"

                if name:
                    if "name" not in node or (node["name"] != "air" and node["name"] != "ignore"):
                        node["name"] = name

                if offset:
                    node["x"] = node["x"] + offset["x"]
                    node["y"] = node["y"] + offset["y"]
                    node["z"] = node["z"] + offset["z"]

                if node["name"] != "ignore":
                    lua = lua + f"minetest.set_node(" \
                                f"{self.mt.lua.dumps({'x': node['x'], 'y': node['y'], 'z': node['z']})}, " \
                                f"{{name=\"{node['name']}\"}})\n"
            self.mt.lua.run(lua)

    def get(self, position: dict, position2: dict = None, relative: bool = True,
            offset: dict = None) -> Union[dict, list]:
        """
        Get the node at given position. It returns a dict with the node definition.
        This contains the "x", "y", "z", "param1", "param2" and "name" keys, where "name" is the node type like
        "default:dirt".

        If also position2 is given, this function returns a list of dicts with node definitions. This list contains a
        cuboid of definitions with the diagonal between position and position2.

        You can get a list of all available node types with :attr:`~miney.Minetest.node.type`.

        :param position: A dict with x,y,z keys
        :param position2: Another point, to get multiple nodes as a list
        :param relative: Return relative or absolute positions
        :param offset: A dict with "x", "y", "z" keys. All node positions will be added with this values.
        :return: The node type on this position
        """
        if type(position) is dict and not position2:  # for a single node
            _position = deepcopy(position)
            if offset:
                _position["x"] = _position["x"] + offset["x"]
                _position["y"] = _position["y"] + offset["y"]
                _position["z"] = _position["z"] + offset["z"]

            node = self.mt.lua.run(f"return minetest.get_node({self.mt.lua.dumps(position)})")
            node["x"] = position["x"]
            node["y"] = position["y"]
            node["z"] = position["z"]
            return node
        elif type(position) is dict and type(position2) is dict:  # Multiple nodes
            _position = deepcopy(position)
            _position2 = deepcopy(position2)

            if offset:
                _position["x"] = _position["x"] + offset["x"]
                _position["y"] = _position["y"] + offset["y"]
                _position["z"] = _position["z"] + offset["z"]
                _position2["x"] = _position2["x"] + offset["x"]
                _position2["y"] = _position2["y"] + offset["y"]
                _position2["z"] = _position2["z"] + offset["z"]

            nodes_relative = """
                node["x"] = x - start_x
                node["y"] = y - start_y
                node["z"] = z - start_z
                """

            nodes_absolute = """
                node["x"] = x
                node["y"] = y
                node["z"] = z
                """

            return self.mt.lua.run(
                f"""
                pos1 = {self.mt.lua.dumps(_position)}
                pos2 = {self.mt.lua.dumps(_position2)}
                minetest.load_area(pos1, pos2)
                nodes = {{}}
                if pos1.x <= pos2.x then start_x = pos1.x end_x = pos2.x else start_x = pos2.x end_x = pos1.x end
                if pos1.y <= pos2.y then start_y = pos1.y end_y = pos2.y else start_y = pos2.y end_y = pos1.y end
                if pos1.z <= pos2.z then start_z = pos1.z end_z = pos2.z else start_z = pos2.z end_z = pos1.z end
                
                for x = start_x, end_x do
                  for y = start_y, end_y do
                    for z = start_z, end_z do
                      node = minetest.get_node({{x = x, y = y, z = z}})
                      {nodes_relative if relative else nodes_absolute}
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
        if type(self.__parent) is not type(self):  # if we don't have a category below
            return self.__getattribute__(item_key)
        if item_key in self.__parent.node_types:
            return item_key
        else:
            if type(item_key) == int:
                return self.__parent.node_types[item_key]
            raise IndexError("unknown node type")

    def __len__(self):
        return len(self.__parent._types_cache)
