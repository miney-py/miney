import miney
from typing import Dict, List


class Node:
    """
    Manipulate and get information's about nodes.
    """
    def __init__(self, mt: miney.Minetest):
        self.mt = mt

    def __repr__(self):
        return '<minetest node functions>'

    def set(self, position: dict, node_name: str) -> None:
        """
        Set node at given position to "node_name" (something like "default:wood").
        You can get a list of all available nodes with :attr:`~pyminetest.Minetest.registered_nodes`

        :param position: a dict with x,y,z keys
        :param node_name: a valid node name
        :return: None
        """
        self.mt.lua.run("minetest.set_node({}, {{name=\"{}\"}})".format(self.mt.lua.dumps(position), node_name))

    def get(self, position: Dict):
        return self.mt.lua.run("return minetest.get_node({})".format(self.mt.lua.dumps(position)))

    @property
    def nodes(self) -> List:
        """
        Get a list of all available nodes/blocks.

        :return: List with all available node names
        """

        return self.mt.lua.run(
            """
            local nodes = {}
            for name, def in pairs(minetest.registered_nodes) do
                table.insert(nodes, name)
            end return nodes
            """
        )


