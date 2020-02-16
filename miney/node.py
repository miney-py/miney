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

    def set(self, position: Union[dict, list], node_type: str = "default:dirt") -> None:
        """
        Set a single or multiple nodes at given position to another node type
        (something like mt.node.type.default.apple).
        You can get a list of all available nodes with :attr:`~miney.Minetest.node.type`

        :Examples:

            Set a single node over :

            >>> pos = mt.player[0].position
            >>> mt.node.set({pos[])

        :param position: a dict with x,y,z keys
        :param node_type: a valid node name
        """
        if type(position) == dict:  # a single node
            if "type" in position:
                node_type = position["type"]
            self.mt.lua.run(f"minetest.set_node({self.mt.lua.dumps(position)}, {{name=\"{node_type}\"}})")
        elif type(position) == list:  # bulk
            chunk_size = 700
            for x in range(0, len(position), chunk_size):
                self.mt.lua.run(
                    f"minetest.bulk_set_node({self.mt.lua.dumps(position[x:x+chunk_size])}, {{name=\"{node_type}\"}})")

    def get(self, position: Dict) -> str:
        """
        Get the node type at given position (something like "default:wood").
        You can get a list of all available node type with :attr:`~miney.Minetest.node.type`

        :param position: a dict with x,y,z keys
        :return: The node type on this position
        """
        return self.mt.lua.run("return minetest.get_node({})".format(self.mt.lua.dumps(position)))

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
