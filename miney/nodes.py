from .node import Node
from .point import Point
from typing import Union, Iterable, Any, TYPE_CHECKING
if TYPE_CHECKING:
    from .luanti import Luanti


class Nodes:
    """
    Manipulate and get information's about node.

    **Nodes manipulation is currently tested for up to 25.000 node, more optimization will come later**

    """
    def __init__(self, luanti: 'Luanti'):
        self.lt = luanti

        self._names_cache = self.lt.lua.run(
            """
            local node = {}
            for name, def in pairs(minetest.registered_nodes) do
                table.insert(node, name)
            end return node
            """
        )
        self._types = NameIterable(self, self._names_cache)

    @property
    def names(self) -> 'NameIterable':
        """
        In Luanti, the type of the node, something like "dirt", is the "name" of this node.

        This property returns all available node names in the game, sorted by categories. In the end it just returns the
        corresponding Luanti name string, so `lt.nodes.names.default.dirt` returns the string 'default:dirt'.
        It's a nice shortcut in REPL, cause with auto completion you have only pressed 2-4 keys to get to your
        type.

        :Examples:

            Directly access a type:

            >>> lt.nodes.names.default.dirt
            'default:dirt'

            Iterate over all available types:

            >>> for node_type in lt.nodes.names:
            >>>     print(node_type)
            default:pine_tree
            default:dry_grass_5
            farming:desert_sand_soil
            ... (there should be over 400 different types)
            >>> print(len(lt.nodes.names))
            421

            Get a list of all types:

            >>> list(lt.nodes.names)
            ['default:pine_tree', 'default:dry_grass_5', 'farming:desert_sand_soil', ...

            Add 99 dirt to player "IloveDirt"'s inventory:

            >>> lt.players.IloveDirt.inventory.add(lt.nodes.names.default.dirt, 99)

        :rtype: :class:`NameIterable`
        :return: :class:`TypeIterable` object with categories. Look at the examples above for usage.
        """
        return self._types

    def set(self, node: Union[Node, list]) -> None:
        """
        Set a single or multiple nodes at a given position.

        You can get a list of all available node names with :attr:`~miney.nodes.Nodes.name`.

        **The `node` parameter can be a single Node object or a list of Node objects for bulk setting.**

        :Examples:

            Replace the node under the first player's feet with dirt:

            >>> from miney import Node, Point
            >>> player_pos = lt.players[0].position
            >>> pos_under_player = player_pos - Point(0, 1, 0)
            >>> dirt_node = Node(pos_under_player.x, pos_under_player.y, pos_under_player.z, name="default:dirt")
            >>> lt.nodes.set(dirt_node)

            Set multiple nodes to create a 2x1 stone platform:

            >>> from miney import Node
            >>> player_pos = lt.players[0].position
            >>> nodes_to_set = [
            ...     Node(player_pos.x + 2, player_pos.y -1, player_pos.z, name="default:stone"),
            ...     Node(player_pos.x + 3, player_pos.y -1, player_pos.z, name="default:stone")
            ... ]
            >>> lt.nodes.set(nodes_to_set)

        :param node: A single :class:`~miney.Node` object or a list of :class:`~miney.Node` objects.
        """
        # Set a single node
        if type(node) is Node:
            self.lt.lua.run(
                f"minetest.set_node({ self.lt.lua.dumps({'x': node.x, 'y': node.y, 'z': node.z}) }, "
                f"{self.lt.lua.dumps({'name': node.name})})"
            )

        # Set many nodes
        elif type(node) is list:

            lua = ""
            # Loop over node, modify name/type, position/offset and generate lua code
            for n in node:
                lua += (f"minetest.set_node("
                        f"{self.lt.lua.dumps({'x': n.x, 'y': n.y, 'z': n.z})}, "
                        f"{self.lt.lua.dumps({'name': n.name})})\n")
            self.lt.lua.run(lua)

    def get(self, point: Union[Point, Node, Iterable]) -> Node | list[Any] | None:
        """
        Get the node at the given position. It returns a node object.
        This contains the "x", "y", "z", "param1", "param2" and "name" attributes, where "name" is the node type like
        "default:dirt".

        If instead of a single point/node a list or tuple with 2 points/nodes is given, this function returns a list of
        nodes. This list contains a cuboid of nodes with the diagonal between the given points.

        Tip: You can get a list of all available node types with :attr:`~miney.Luanti.node.type`.

        :param point: A Point object
        :return: The node type on this position
        """
        if isinstance(point, Point):  # for a single node
            pos_dict = {'x': point.x, 'y': point.y, 'z': point.z}
            node_data = self.lt.lua.run(
                f"return minetest.get_node({self.lt.lua.dumps(pos_dict)})")
            node = Node(point.x, point.y, point.z, **node_data, luanti=self.lt)
            return node
        elif isinstance(point, (list, tuple)) and len(point) == 2:  # Multiple nodes
            pos1_dict = {'x': point[0].x, 'y': point[0].y, 'z': point[0].z}
            pos2_dict = {'x': point[1].x, 'y': point[1].y, 'z': point[1].z}
            lnodes = self.lt.lua.run(  # We sort them by the smallest coordinates and get them node per node
                f"""
                pos1 = {self.lt.lua.dumps(pos1_dict)}
                pos2 = {self.lt.lua.dumps(pos2_dict)}
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
                nodes.append(Node(n["x"], n["y"], n["z"], n["name"], n["param1"], n["param2"], luanti=self.lt))

            return nodes
        return None

    def __repr__(self):
        return '<Luanti node functions>'


class NameIterable:
    """Node names, implemented as iterable for easy autocomplete in the interactive shell"""
    def __init__(self, parent, nodes_types=None):

        self._parent = parent

        if nodes_types:

            # get type categories list
            type_categories = {}
            for ntype in nodes_types:
                if ":" in ntype:
                    type_categories[ntype.split(":")[0]] = ntype.split(":")[0]
            for tc in dict.fromkeys(type_categories):
                self.__setattr__(tc, NameIterable(parent))

            # values to categories
            for ntype in nodes_types:
                if ":" in ntype:
                    self.__getattribute__(ntype.split(":")[0]).__setattr__(ntype.split(":")[1], ntype)
                else:
                    self.__setattr__(ntype, ntype)  # for 'air' and 'ignore'

    def __iter__(self):
        return iter(self._parent._names_cache)

    def __getitem__(self, item_key):
        if type(self._parent) is not type(self):  # if we don't have a category below
            return self.__getattribute__(item_key)
        if item_key in self._parent.node_types:
            return item_key
        else:
            if type(item_key) == int:
                return self._parent.node_types[item_key]
            raise IndexError("unknown node type")

    def __len__(self):
        return len(self._parent._names_cache)
