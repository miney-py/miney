API
=================================

Miney provides many shortcuts inside it's api.

You can access the node manipulation on two different ways:

:Example:

    >>> import miney

    >>> mt = miney.Minetest()
    >>> mt.node.get(0, 0, 0)
    >>> mt.node.set(miney.Node(0, 0, 0, "default:dirt"))

thats a shortcut for

:Example:

    >>> import miney

    >>> mt = miney.Minetest()
    >>> nf = miney.NodeFunctions(mt)
    >>> nf.get(miney.Point(0, 0, 0))


.. rubric:: Objects

.. toctree::

   minetest
   point
   helpers
   exceptions

.. rubric:: Indices and tables

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
