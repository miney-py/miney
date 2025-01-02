API
=================================

Miney provides many shortcuts inside it's api.

You can access the node manipulation on two different ways:

:Example:

    >>> import miney

    >>> lt = miney.Luanti()
    >>> lt.node.get(0, 0, 0)
    >>> lt.node.set(miney.Node(0, 0, 0, "default:dirt"))

thats a shortcut for

:Example:

    >>> import miney

    >>> lt = miney.Luanti()
    >>> nf = miney.NodeFunctions(lt)
    >>> nf.get(miney.Point(0, 0, 0))


.. rubric:: Objects

.. toctree::

   Luanti
   point
   helpers
   exceptions

.. rubric:: Indices and tables

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
