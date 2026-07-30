Nodes
=====

The ``Nodes`` object provides methods to get and manipulate nodes in the game world.
When you retrieve a node, it is returned as a :class:`~miney.node.Node` object, which contains its position, name, and other properties.

.. rubric:: Three ways to build

Picking the right one is the difference between a wall appearing and a wall taking three
minutes to appear — and between a chest you can open and one you cannot.

:meth:`~miney.Nodes.set` writes blocks into the world, one instruction per block, about
700 a second. It is the everyday way to put a block somewhere.

:meth:`~miney.Nodes.fill` fills a box with one kind of block. It sends the two corners
and a name, and the server does the rest, so **the size of the box does not reach the
network at all**: a floor of four thousand blocks and a hillside of three million cost
the same to ask for. Roughly 4,700,000 blocks a second. For floors, walls, towers and
clearing ground, which is most of building, that is exactly what you want.

:meth:`~miney.Nodes.place` places blocks the way a *player* would. It is the slow one —
the game does real work per block — and it is the only one where the block ends up
working. Use it for the few blocks that have a moving part.

.. important::

   ``set`` and ``fill`` write the block and nothing else. The game's own placement code
   never runs, so a door gets no top half, a torch faces nowhere, a chest has no
   inventory at all and a sapling never grows. That is fine for the blocks those two are
   for, and it is why :meth:`~miney.Nodes.place` exists for the rest.

.. code-block:: python

   from miney import Point, Node

   lt.nodes.fill(Point(0, 10, 0), Point(63, 10, 63), "mcl_core:obsidian")  # a floor
   lt.nodes.fill(Point(0, 11, 0), Point(63, 74, 63), "air")                # clear above it
   lt.nodes.set(Node(32, 11, 32, name="mcl_core:stone"))                   # one block
   lt.nodes.place(Node(33, 11, 32, name="mcl_chests:chest"))               # a working chest

.. rubric:: Finding what is already there

:meth:`~miney.Nodes.find` gives you the closest block of a kind around a point, and
:meth:`~miney.Nodes.find_in` gives you every one of them inside a box. Both answer with
:class:`~miney.node.Node` objects, which are also positions, so what comes back goes
straight into the next call.

.. code-block:: python

   player = lt.players[0]

   water = lt.nodes.find("group:water", near=player.position, radius=20)
   if water:
       lt.chat.send_to_all(f"Water at {water.x}, {water.y}, {water.z}")

   for tree in lt.nodes.find_in(Point(0, 0, 0), Point(50, 30, 50), "group:tree"):
       lt.nodes.dig(tree)

.. rubric:: How dark is it here?

.. code-block:: python

   if lt.nodes.light_at(player.position) < 8:
       lt.chat.send_to_player(player.name, "Dark enough for monsters. Bring a torch.")

:meth:`~miney.Nodes.light_at` answers with a number from 0 to 15, counting sunlight and
torches together, so it changes as the sun moves. Measure the *air* above the ground —
the light inside a solid block is always 0.

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

