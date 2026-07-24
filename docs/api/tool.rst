Tools
=====

The ``tool`` attribute of the :class:`~miney.Luanti` object lists every tool the running game knows about.

Like :attr:`~miney.Nodes.names`, it exists so you can find the name of a tool by pressing :kbd:`Tab` instead of
looking it up somewhere:

:Example:

    >>> lt.tool.  # Press Tab
    >>> lt.tool.default.  # Press Tab
    >>> lt.tool.default.pick_mese
    'default:pick_mese'

.. autoclass:: miney.ToolIterable
   :members:
