Node
====

A representation of a node in the game world, inheriting from :class:`~miney.point.Point`.

In addition to coordinates, a node has a ``name`` (e.g., ``"default:stone"``) and ``param1`` and ``param2`` attributes, which are used for node-specific data.

If a node is a container (like a chest), it provides access to its :class:`~miney.inventory.Inventory` through the ``inventory`` property.

.. autoclass:: miney.node.Node
   :members:

.. toctree::
   :maxdepth: 1

   inventory