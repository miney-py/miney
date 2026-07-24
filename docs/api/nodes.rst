Nodes
=====

The ``Nodes`` object provides methods to get and manipulate nodes in the game world.
When you retrieve a node, it is returned as a :class:`~miney.node.Node` object, which contains its position, name, and other properties.

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

