Nodes
=====

The ``Nodes`` object provides methods to get and manipulate nodes in the game world.
When you retrieve a node, it is returned as a :class:`~miney.node.Node` object, which contains its position, name, and other properties.

.. rubric:: Two ways to build

There are two, and picking the right one is the difference between a wall appearing and
a wall taking three minutes to appear.

:meth:`~miney.Nodes.set` places blocks the way the game does. Every block is placed
properly: a chest gets its inventory, sand falls, water flows, a door works. It sends one
instruction per block, so its cost grows with the number of blocks — about 700 a second.
Use it for one block, or for a few hundred, or whenever the blocks have to *behave*.

:meth:`~miney.Nodes.fill` fills a box with one kind of block. It sends the two corners
and a name, and the server does the rest, so **the size of the box does not reach the
network at all**: a floor of four thousand blocks and a hillside of three million cost
the same to ask for. Roughly 4,700,000 blocks a second. In exchange it writes blocks and
nothing else — no chest inventories, no falling sand, no flowing water. For floors,
walls, towers and clearing ground, which is most of building, that is exactly what you
want.

.. code-block:: python

   from miney import Point, Node

   lt.nodes.fill(Point(0, 10, 0), Point(63, 10, 63), "mcl_core:obsidian")  # a floor
   lt.nodes.fill(Point(0, 11, 0), Point(63, 74, 63), "air")                # clear above it
   lt.nodes.set(Node(32, 11, 32, name="mcl_chests:chest"))                 # a working chest

.. autoclass:: miney.Nodes
   :members:

.. rubric:: Node names

:attr:`~miney.Nodes.names` hands you this object. Its whole job is to make node names discoverable with
:kbd:`Tab` in the Python shell, so you never have to memorise a string like ``"default:dirt"``.

.. autoclass:: miney.nodes.NameIterable
   :members:

.. toctree::
   :maxdepth: 1

   node

