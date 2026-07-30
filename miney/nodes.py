from math import floor
from collections.abc import Iterable, Mapping
from .exceptions import DataError
from .node import Node
from .point import Point
from typing import Union, Any, TYPE_CHECKING
if TYPE_CHECKING:
    from .luanti import Luanti


def _load_areas(positions: Iterable[tuple[int, int, int]]) -> str:
    """
    Build the Lua that makes sure the map is loaded where nodes are about to be set.

    ``minetest.set_node`` does nothing at all in a part of the world the server does
    not currently have in memory. It does not load it, it does not complain, and it
    does not raise - it writes a line into the server log and drops the node. Building
    anything away from a player therefore produced no blocks and no error.

    The engine loads whole 16x16x16 mapblocks, so this asks for each *distinct*
    mapblock exactly once rather than once per node. That keeps the extra Lua to a few
    dozen lines for a normal build, and keeps it bounded for nodes scattered across the
    world - where loading one box around all of them could mean loading half a
    continent.

    :param positions: The ``(x, y, z)`` of every node about to be written.
    :return: Lua source, one ``load_area`` per mapblock, or ``""`` if there is nothing
        to load.
    """
    seen: set[tuple[int, int, int]] = set()
    lines = []
    for x, y, z in positions:
        # Shifting floors towards negative infinity, which is the same way mapblock
        # boundaries run. Integer division would round towards zero and put everything
        # just below y=0 in the wrong block.
        block = (floor(x) >> 4, floor(y) >> 4, floor(z) >> 4)
        if block in seen:
            continue
        seen.add(block)
        lines.append(
            f"minetest.load_area({{x={block[0] * 16}, "
            f"y={block[1] * 16}, z={block[2] * 16}}})"
        )
    return "\n".join(lines)


#: Most blocks written by one call to the server. A ``VoxelManip`` holds the whole box
#: in memory as a Lua array while it works, so a big enough box would be a memory
#: problem on the server rather than on the wire. :meth:`Nodes.fill` splits anything
#: larger into slabs instead of refusing it, so this number never reaches the user.
_MAX_FILL_VOLUME = 4_000_000

_FILL_LUA = """
local p1 = {{x = {x1}, y = {y1}, z = {z1}}}
local p2 = {{x = {x2}, y = {y2}, z = {z2}}}
local vm = VoxelManip()
local emin, emax = vm:read_from_map(p1, p2)
local area = VoxelArea:new{{MinEdge = emin, MaxEdge = emax}}
local data = vm:get_data()
local cid = minetest.get_content_id({name})
local n = 0
for z = p1.z, p2.z do
    for y = p1.y, p2.y do
        local vi = area:index(p1.x, y, z)
        for _ = p1.x, p2.x do
            data[vi] = cid
            vi = vi + 1
            n = n + 1
        end
    end
end
vm:set_data(data)
vm:write_to_map(true)
return n
"""


#: Reads a cuboid and packs the answer instead of describing every node separately.
#:
#: The obvious version builds one Lua table per node with five keys in it and lets the
#: bridge turn that into JSON. Measured over 32,768 nodes of real terrain that took
#: 848 ms, and about two thirds of it was the packing rather than the reading - swapping
#: ``minetest.get_node`` for a VoxelManip changes nothing measurable, because the engine
#: was never the slow part.
#:
#: So the reader stays and the answer changes. Names are sent once and referred to by
#: number afterwards, and a stretch of identical neighbours collapses into one token, in
#: the order the nodes are walked. Terrain is mostly stone next to stone and air next to
#: air, so this is where the size goes: 510 KB becomes 55 KB, and 848 ms becomes 11 ms.
_GET_LUA = """
local p1, p2 = {pos1}, {pos2}
local x1, x2 = math.min(p1.x, p2.x), math.max(p1.x, p2.x)
local y1, y2 = math.min(p1.y, p2.y), math.max(p1.y, p2.y)
local z1, z2 = math.min(p1.z, p2.z), math.max(p1.z, p2.z)
minetest.load_area({{x=x1, y=y1, z=z1}}, {{x=x2, y=y2, z=z2}})

local get_node = minetest.get_node
local seen, palette, runs = {{}}, {{}}, {{}}
local last, run = nil, 0

for x = x1, x2 do
  for y = y1, y2 do
    for z = z1, z2 do
      local node = get_node({{x = x, y = y, z = z}})
      local id = seen[node.name]
      if not id then
        palette[#palette + 1] = node.name
        id = #palette
        seen[node.name] = id
      end
      local token = id .. "," .. node.param1 .. "," .. node.param2
      if token == last then
        run = run + 1
      else
        if last then runs[#runs + 1] = last .. "x" .. run end
        last, run = token, 1
      end
    end
  end
end
if last then runs[#runs + 1] = last .. "x" .. run end

return table.concat(palette, " ") .. "|" .. table.concat(runs, " ")
"""


def _decode_nodes(packed: str, corner1: tuple[int, int, int],
                  corner2: tuple[int, int, int], luanti: 'Luanti') -> list[Node]:
    """
    Turn the packed answer from :data:`_GET_LUA` back into :class:`~miney.node.Node`.

    The coordinates are not transmitted - they are walked in the same order the server
    walked them, x outermost and z innermost, which is the order
    :meth:`Nodes.get` has always returned.

    :param packed: ``"name name name|index,param1,param2xcount ..."``.
    :param corner1: The lower corner of the region that was asked for.
    :param corner2: The upper corner.
    :param luanti: Bound into every node, so ``node.inventory`` works.
    :return: One Node per position, in the documented order.
    :raises DataError: If the answer does not describe exactly this region.
    """
    x1, y1, z1 = corner1
    x2, y2, z2 = corner2
    expected = (x2 - x1 + 1) * (y2 - y1 + 1) * (z2 - z1 + 1)

    names_part, separator, runs_part = packed.partition("|")
    if not separator:
        raise DataError(
            "The server's answer for this region is not in the expected form.")
    names = names_part.split(" ") if names_part else []

    nodes: list[Node] = []
    x, y, z = x1, y1, z1
    try:
        for token in runs_part.split(" "):
            if not token:
                continue
            head, _, count = token.rpartition("x")
            index, param1, param2 = head.split(",")
            name = names[int(index) - 1]
            param1, param2 = int(param1), int(param2)

            for _ in range(int(count)):
                nodes.append(Node(x, y, z, name, param1, param2, luanti=luanti))
                z += 1
                if z > z2:
                    z = z1
                    y += 1
                    if y > y2:
                        y = y1
                        x += 1
    except (ValueError, IndexError) as e:
        raise DataError(f"Could not read the server's answer for this region: {e}")

    if len(nodes) != expected:
        raise DataError(
            f"The server described {len(nodes)} nodes for a region of {expected}.")
    return nodes


def _slabs(p1: tuple[int, int, int], p2: tuple[int, int, int]):
    """
    Cut a box into pieces small enough for one ``VoxelManip`` each.

    Slicing along z first keeps each piece a contiguous run of the wide axes, which is
    what the fill loop walks anyway. A box so wide that a single z-layer is still too
    large gets sliced along y as well - that needs an x times y of four million, which
    no real build has, but a loop that only *usually* terminates is not worth writing.

    :param p1: The lower corner, already sorted and integral.
    :param p2: The upper corner.
    :return: Yields ``(corner, corner)`` pairs covering the box exactly once.
    """
    dx = p2[0] - p1[0] + 1
    dy = p2[1] - p1[1] + 1

    z_step = max(1, _MAX_FILL_VOLUME // max(1, dx * dy))
    y_step = max(1, _MAX_FILL_VOLUME // max(1, dx))

    for z in range(p1[2], p2[2] + 1, z_step):
        z_end = min(z + z_step - 1, p2[2])
        if dx * dy <= _MAX_FILL_VOLUME:
            yield (p1[0], p1[1], z), (p2[0], p2[1], z_end)
            continue
        for y in range(p1[1], p2[1] + 1, y_step):
            yield (p1[0], y, z), (p2[0], min(y + y_step - 1, p2[1]), z_end)


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
        self._types = NameIterable(self._names_cache)

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

        :return: An object with all node names, grouped by category. Look at the examples above for usage.
        """
        return self._types

    def set(self, node: Union[Node, Iterable[Node]]) -> None:
        """
        Set a single or multiple nodes at a given position.

        You can get a list of all available node names with :attr:`~miney.Nodes.names`.

        **The `node` parameter can be a single Node object, or any collection of Node
        objects - a list, a tuple, a set or a generator - for bulk setting.**

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

        :param node: A single :class:`~miney.node.Node` object, or a collection of
            :class:`~miney.node.Node` objects.
        :raises TypeError: If something other than a Node or a collection of Nodes is
            passed.
        """
        # A Node is itself iterable (it is a Point), so it has to be recognised first.
        if isinstance(node, Node):
            nodes = [node]
        # A str and a dict are iterable too, and neither is a collection of nodes.
        elif isinstance(node, Iterable) and not isinstance(node, (str, bytes, Mapping)):
            nodes = list(node)  # so a generator survives being walked twice below
        else:
            raise TypeError(
                f"'node' must be a Node or a collection of Nodes, got "
                f"{type(node).__name__}. A node name alone is not enough - it needs a "
                f"position: lt.nodes.set(Node(10, 20, 30, name='default:dirt'))"
            )

        for n in nodes:
            if not isinstance(n, Node):
                raise TypeError(
                    f"Every element must be a Node, got {type(n).__name__}. A Point "
                    f"carries no node name: Node(point.x, point.y, point.z, "
                    f"name='default:dirt')"
                )

        if not nodes:  # nothing to do, and an empty run() would still cost a round trip
            return

        lua = _load_areas([(n.x, n.y, n.z) for n in nodes]) + "\n"
        # Loop over node, modify name/type, position/offset and generate lua code
        for n in nodes:
            lua += (f"minetest.set_node("
                    f"{self.lt.lua.dumps({'x': n.x, 'y': n.y, 'z': n.z})}, "
                    f"{self.lt.lua.dumps({'name': n.name})})\n")
        self.lt.lua.run(lua, wait=False)

    def fill(self, start: Point, end: Point, name: str) -> int:
        """
        Fill a box with one kind of block, at any size.

        This is the fast way to build. :meth:`set` sends one line of Lua per block, so
        a wall costs as much network as it has blocks in it. ``fill`` sends the two
        corners and a name - about eighty bytes - and the server does the writing with
        ``VoxelManip``, its bulk map interface. **Nothing about the size of the box
        travels**, so a 128x128x64 region costs exactly as much bandwidth as one block.

        Measured against a local server: :meth:`set` writes about 700 blocks a second,
        ``fill`` about 4,700,000. Levelling a 193x193x76 site takes 0.4 seconds.

        .. important::

            ``fill`` writes blocks and nothing else. The engine's bulk interface skips
            the machinery that makes blocks *behave*:

            - **No block callbacks.** A chest placed this way has no inventory at all,
              because the code that gives it one never runs. The same goes for
              furnaces, signs, doors, beds - anything with a working part.
            - **Nothing falls.** Sand and gravel with no support stay in the air until
              something disturbs them.
            - **Old contents stay behind.** Filling over a chest with air removes the
              chest but leaves what was inside it in the map, and a chest built at the
              same spot later inherits it.
            - **Liquids do not flow.** Water placed this way sits still.

            None of that matters for the thing ``fill`` is for - floors, walls, towers,
            clearing ground, terrain. For blocks that need to work, use :meth:`set`,
            which goes through the ordinary placement path.

        :Examples:

            A 64x64 obsidian floor at y=10:

            >>> from miney import Point
            >>> lt.nodes.fill(Point(0, 10, 0), Point(63, 10, 63), "mcl_core:obsidian")
            4096

            Clear the air above it - 262,144 blocks, one call, no faster or slower
            than the floor was:

            >>> lt.nodes.fill(Point(0, 11, 0), Point(63, 74, 63), "air")
            262144

            A pillar next to the first player:

            >>> here = lt.players[0].position
            >>> lt.nodes.fill(here + Point(2, 0, 0), here + Point(2, 20, 0),
            ...               lt.nodes.names.mcl_core.glass)
            21

        :param start: One corner of the box.
        :param end: The opposite corner. The two may be given in any order.
        :param name: What to fill with, e.g. ``"mcl_core:obsidian"`` or ``"air"``.
            Use :attr:`~miney.Nodes.names` to find one with autocomplete.
        :return: How many blocks were written.
        :raises TypeError: If the corners are not points, or the name is not a string.
        :raises ValueError: If this server has no block of that name.
        """
        for label, corner in (("start", start), ("end", end)):
            if not isinstance(corner, Point):
                raise TypeError(
                    f"'{label}' must be a Point, got {type(corner).__name__}. "
                    f"lt.nodes.fill(Point(0, 10, 0), Point(63, 10, 63), 'air')"
                )
        if not isinstance(name, str):
            raise TypeError(f"'name' must be str, got {type(name).__name__}.")
        if name not in self._names_cache:
            raise ValueError(
                f"This server has no block called {name!r}. Find one with "
                f"lt.nodes.names - it autocompletes, so lt.nodes.names.mcl_core.stone "
                f"finds 'mcl_core:stone' in a few keystrokes."
            )

        p1 = (min(floor(start.x), floor(end.x)), min(floor(start.y), floor(end.y)),
              min(floor(start.z), floor(end.z)))
        p2 = (max(floor(start.x), floor(end.x)), max(floor(start.y), floor(end.y)),
              max(floor(start.z), floor(end.z)))

        written = 0
        for box in _slabs(p1, p2):
            written += self.lt.lua.run(
                _FILL_LUA.format(
                    x1=box[0][0], y1=box[0][1], z1=box[0][2],
                    x2=box[1][0], y2=box[1][1], z2=box[1][2],
                    name=self.lt.lua.dumps(name),
                ),
                timeout=120,
            ) or 0
        return written

    def get(self, point: Union[Point, Node, Iterable]) -> Node | list[Any]:
        """
        Get the node at the given position. It returns a node object.
        This contains the "x", "y", "z", "param1", "param2" and "name" attributes, where "name" is the node type like
        "default:dirt".

        If instead of a single point/node a list or tuple with 2 points/nodes is given, this function returns a list of
        nodes. This list contains a cuboid of nodes with the diagonal between the given points.

        The nodes come back in a fixed order - x changes slowest, then y, and z fastest -
        so the node at an offset inside the box is at a position you can work out:
        ``index = dx * ny * nz + dy * nz + dz``. Iterating the list is usually easier.

        A whole region travels as one answer, and identical neighbours are sent once
        rather than each in turn, which is what terrain mostly consists of. Reading
        32,768 nodes takes about 30 milliseconds. Most of that is now building the
        :class:`~miney.node.Node` objects on this side, so ask for the region you want
        rather than the region you might want.

        Tip: You can get a list of all available node names with :attr:`~miney.Nodes.names`.

        :param point: A Point object, or a list/tuple of exactly two of them for a cuboid
        :return: The node on this position, or the list of nodes in the cuboid
        :raises TypeError: If something other than a Point or a pair of Points is passed
        :raises ValueError: If the pair does not have exactly two entries
        :raises miney.exceptions.DataError: If the server's answer does not describe the
            region that was asked for
        """
        if isinstance(point, Point):  # for a single node
            pos_dict = {'x': point.x, 'y': point.y, 'z': point.z}
            node_data = self.lt.lua.run(
                f"return minetest.get_node({self.lt.lua.dumps(pos_dict)})")
            node = Node(point.x, point.y, point.z, **node_data, luanti=self.lt)
            return node
        elif isinstance(point, (list, tuple)):  # Multiple nodes
            if len(point) != 2:
                raise ValueError(
                    f"A cuboid is described by exactly two opposite corners, got "
                    f"{len(point)}. Pass one Point for a single node, or two for the "
                    f"box between them."
                )
            pos1_dict = {'x': point[0].x, 'y': point[0].y, 'z': point[0].z}
            pos2_dict = {'x': point[1].x, 'y': point[1].y, 'z': point[1].z}
            packed = self.lt.lua.run(
                _GET_LUA.format(pos1=self.lt.lua.dumps(pos1_dict),
                                pos2=self.lt.lua.dumps(pos2_dict)),
                timeout=60)
            corner1 = (min(floor(point[0].x), floor(point[1].x)),
                       min(floor(point[0].y), floor(point[1].y)),
                       min(floor(point[0].z), floor(point[1].z)))
            corner2 = (max(floor(point[0].x), floor(point[1].x)),
                       max(floor(point[0].y), floor(point[1].y)),
                       max(floor(point[0].z), floor(point[1].z)))
            return _decode_nodes(packed, corner1, corner2, self.lt)
        raise TypeError(
            f"'point' must be a Point or Node, or a list of two of them for a cuboid, "
            f"got {type(point).__name__}."
        )

    def __repr__(self):
        return '<Luanti node functions>'


class NameIterable:
    """
    Node names, as attributes you can find with TAB instead of having to remember them.

    ``lt.nodes.names.default.dirt`` is the string ``'default:dirt'``. The first level is
    the mod a block comes from, the second is the block, and typing a dot and pressing
    TAB in an interactive shell shows what there is. Being able to *find* the name is
    the whole point - nobody guesses ``'default:stone_with_mese'``.

    It is also a list, so ``len()``, ``for`` and ``[0]`` work, and a dictionary, so
    ``lt.nodes.names["default:dirt"]`` and ``lt.nodes.names.default["dirt"]`` both give
    the same string back.

    You do not create this yourself. :attr:`lt.nodes.names <miney.Nodes.names>` is one,
    :attr:`lt.tool <miney.Luanti.tool>` and :attr:`lt.items <miney.Luanti.items>` are
    the same thing for tools and for everything else.
    """

    def __init__(self, names=None):
        """
        :param names: Every full name, ``'mod:thing'``. Left out for a level that gets
                      its names put in afterwards.
        """
        # Sorted, so that lt.nodes.names[0] is the same name on every run. Luanti hands
        # them over out of a Lua table, which has no order worth relying on.
        self._names = sorted(names or [])

        categories: dict[str, list[str]] = {}
        for name in self._names:
            mod, colon, short = name.partition(":")
            if not colon:
                # 'air' and 'ignore' belong to no mod and sit at the top level.
                setattr(self, name, name)
                continue
            categories.setdefault(mod, []).append(name)

        for mod, mod_names in categories.items():
            # Built empty and filled here rather than by another round of __init__:
            # the names below still carry their colon, so letting the constructor sort
            # them again would build a 'default' inside 'default' forever.
            category = NameIterable()
            category._names = mod_names
            for name in mod_names:
                setattr(category, name.partition(":")[2], name)
            setattr(self, mod, category)

    def __repr__(self):
        return f"<Luanti names: {len(self._names)}>"

    def __iter__(self):
        return iter(self._names)

    def __getitem__(self, item_key):
        """
        :param item_key: A full name, the short name below a mod, or a position.
        :return: The name as a string, or the level below for a mod name.
        :raises KeyError: If there is no such name.
        :raises IndexError: If the position is past the end.
        """
        if isinstance(item_key, int):
            return self._names[item_key]
        if item_key in self._names:
            return item_key
        value = getattr(self, item_key, None) if isinstance(item_key, str) else None
        if isinstance(value, (str, NameIterable)):
            return value
        raise KeyError(item_key)

    def __len__(self):
        return len(self._names)
