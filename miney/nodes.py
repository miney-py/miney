import miney
from miney import Node, Point
from typing import Union, Iterable


class Nodes:
    """
    Manipulate and get information's about node.

    **Nodes manipulation is currently tested for up to 25.000 node, more optimization will come later**

    """
    def __init__(self, mt: miney.Minetest):
        self.mt = mt

        self._types_cache = self.mt.lua.run(
            """
            local node = {}
            for name, def in pairs(minetest.registered_nodes) do
                table.insert(node, name)
            end return node
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

    def set(self, node: Union[Node, list]) -> None:
        """
        Set a single or multiple nodes at given position to another node type
        (something like mt.nodes.type.default.apple).
        You can get a list of all available node types with :attr:`~miney.Minetest.node.type`

        **The nodes parameter can be a single Node object or a list of Node objects for bulk spawning.**

        :Examples:

            Replace the node under the first players feet with dirt:

            >>> from miney import Node
            >>> pos = Node(mt.player[0].position.x, mt.player[0].position.y - 1, mt.player[0].position.z, "default:dirt")
            >>> mt.nodes.set(mt.player[0].position)

        :param node: A dict or a list of dicts with node definitions
        """
        # Set a single node
        if type(node) is Node:
            self.mt.lua.run(
                f"minetest.set_node({ self.mt.lua.dumps({'x': node.x, 'y': node.y, 'z': node.z}) }, "
                f"{{name=\"{ node.name }\"}})"
            )

        # Set many blocks
        elif type(node) is list:

            lua = ""
            # Loop over node, modify name/type, position/offset and generate lua code
            for n in node:
                lua = lua + f"minetest.set_node(" \
                            f"{self.mt.lua.dumps({'x': n.x, 'y': n.y, 'z': n.z})}, " \
                            f"{{name=\"{n.name}\"}})\n"
            self.mt.lua.run(lua)

    def get(self, point: Union[Point, Iterable]) -> Union[Node, list]:
        """
        Get the node at given position. It returns a dict with the node definition.
        This contains the "x", "y", "z", "param1", "param2" and "name" keys, where "name" is the node type like
        "default:dirt".

        If also position2 is given, this function returns a list of dicts with node definitions. This list contains a
        cuboid of definitions with the diagonal between position and position2.

        You can get a list of all available node types with :attr:`~miney.Minetest.node.type`.

        :param point: A Point object
        :return: The node type on this position
        """
        if isinstance(point, Point):  # for a single node
            node = Node(point.x, point.y, point.z, **self.mt.lua.run(
                f"return minetest.get_node({self.mt.lua.dumps(point.__dict__)})"))
            return node
        elif isinstance(point, Iterable):  # Multiple node
            lnodes = self.mt.lua.run(  # We sort them by the smallest coordinates and get them node per node
                f"""
                pos1 = {self.mt.lua.dumps(dict(point[0]))}
                pos2 = {self.mt.lua.dumps(dict(point[1]))}
                minetest.load_area(pos1, pos2)
                nodes = {{}}
                if pos1.x <= pos2.x then start_x = pos1.x end_x = pos2.x else start_x = pos2.x end_x = pos1.x end
                if pos1.y <= pos2.y then start_y = pos1.y end_y = pos2.y else start_y = pos2.y end_y = pos1.y end
                if pos1.z <= pos2.z then start_z = pos1.z end_z = pos2.z else start_z = pos2.z end_z = pos1.z end
                for x = start_x, end_x do
                  for y = start_y, end_y do
                    for z = start_z, end_z do
                      node = minetest.get_node({{x = x, y = y, z = z}})
                      node["x"] = x
                      node["y"] = y
                      node["z"] = z
                      nodes[#nodes+1] = node  -- append node
                    end
                  end
                end
                return nodes""", timeout=60)
            nodes = []
            for n in lnodes:
                nodes.append(Node(n["x"], n["y"], n["z"], n["name"], n["param1"], n["param2"]))

            return nodes

    def __repr__(self):
        return '<minetest node functions>'


class TypeIterable:
    """Nodes type, implemented as iterable for easy autocomplete in the interactive shell"""
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
