Node
====

A representation of a node in the game world, inheriting from :class:`~miney.point.Point`.

In addition to coordinates, a node has a ``name`` (e.g., ``"default:stone"``) and ``param1`` and ``param2`` attributes, which are used for node-specific data.

If a node is a container (like a chest), it provides access to its :class:`~miney.inventory.Inventory` through the ``inventory`` property.

What the game wrote on a block
------------------------------

Some blocks carry a small table of text that the game filled in — a sign's words, a
chest's contents, the line you see when you point at something. ``node.meta`` is that
table, and it behaves like a dictionary:

.. code-block:: python

    sign = lt.nodes.get(Point(0, 10, 0))
    sign.meta["text"] = "This way"

.. warning::

   These keys belong to the game. :attr:`player.storage <miney.Player.storage>` is the
   store that is yours — this one is the block's, and clearing it clears what the game
   put there.

.. autoclass:: miney.node.Node
   :members:

.. toctree::
   :maxdepth: 1

   inventory