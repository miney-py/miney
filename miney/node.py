import miney
from typing import Dict, List


class Node:
    """
    Manipulate and get information's about nodes.
    """
    def __init__(self, mt: miney.Minetest):
        self.mt = mt
        self._node_types_cache = None

        self.types = Types(self._node_types)
        """All available node types in the game, sorted by categories.
        
        Example::
        
            import miney
            mt = miney.Minetest()
            
            mt.node.types.default.dirt
            
        Example to iterate over all available types::
        
            import miney
            mt = miney.Minetest()
            
            for node_type in mt.node.types:
                print(node_type)
                
            >>> default:pine_tree
            >>> default:dry_grass_5
            >>> farming:desert_sand_soil
            >>> ... (there should be over 400 different types)
            
            print(len(mt.node.types))
            >>> 421
            
        """
        # todo: Node - Example to add types to player inventories

    def __repr__(self):
        return '<minetest node functions>'

    def set(self, position: dict, node_name: str) -> None:
        """
        Set node at given position to a node type (something like mt.node.types.default.apple).
        You can get a list of all available nodes with :attr:`~miney.Minetest.node.types`

        :param position: a dict with x,y,z keys
        :param node_name: a valid node name
        :return: None
        """
        self.mt.lua.run("minetest.set_node({}, {{name=\"{}\"}})".format(self.mt.lua.dumps(position), node_name))

    def get(self, position: Dict) -> str:
        """
        Get the node type at given position (something like "default:wood").
        You can get a list of all available node types with :attr:`~miney.Minetest.node.types`

        :param position: a dict with x,y,z keys
        :return: The node type on this position
        """
        return self.mt.lua.run("return minetest.get_node({})".format(self.mt.lua.dumps(position)))

    @property
    def _node_types(self) -> List:
        """
        Get a list of all available nodes/blocks.

        :return: List with all available node names
        """
        if not self._node_types_cache:
            self._node_types_cache = self.mt.lua.run(
                """
                local nodes = {}
                for name, def in pairs(minetest.registered_nodes) do
                    table.insert(nodes, name)
                end return nodes
                """
            )
        return self._node_types_cache


class Types:
    """Node types, implemented as iterable for easy autocomplete in the interactive shell"""
    def __init__(self, nodes_types=None):
        if nodes_types:
            self.node_types = nodes_types

            # get type categories list
            type_categories = {}
            for ntype in nodes_types:
                if ":" in ntype:
                    type_categories[ntype.split(":")[0]] = ntype.split(":")[0]
            for tc in dict.fromkeys(type_categories):
                self.__setattr__(tc, Types())

            # values to categories
            for ntype in nodes_types:
                if ":" in ntype:
                    self.__getattribute__(ntype.split(":")[0]).__setattr__(ntype.split(":")[1], ntype)
                else:
                    self.__setattr__(ntype, ntype)  # for 'air' and 'ignore'

    def __iter__(self):
        return iter(self.node_types)

    def __getitem__(self, item_key):
        if item_key in self.node_types:
            return item_key
        else:
            raise IndexError("unknown node type")

    def __len__(self):
        return len(self.node_types)