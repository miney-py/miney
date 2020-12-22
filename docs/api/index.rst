API
=================================

Miney provides many shortcuts inside it's api.

You can access the node manipulation on two different ways:

:Example:

    >>> import miney

    >>> mt = miney.Minetest()
    >>> mt.node.get(0, 0, 0)
    >>> mt.node.set({"x": 0, "y": 0, "z": 0, "name": "default:dirt"})

thats a shortcut for

:Example:

    >>> import miney

    >>> mt = miney.Minetest()
    >>> nf = miney.NodeFunctions(mt)
    >>> nf.get(0, 0, 0)


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
