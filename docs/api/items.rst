Items
=====

``lt.items`` is every name that can be in a player's hand, as attributes you find with
TAB instead of remembering them.

:Example:

    >>> lt.items.default.stick
    'default:stick'
    >>> lt.items.default.torch
    'default:torch'
    >>> lt.items.default.pick_mese
    'default:pick_mese'

Luanti calls all of it *items*, and there are three kinds. Miney has a separate list for
two of them, and this one has all three together:

.. list-table::
   :header-rows: 1
   :widths: 25 35 40

   * - Kind
     - Example
     - Where else to find it
   * - Blocks
     - ``default:torch``
     - :attr:`lt.nodes.names <miney.Nodes.names>`
   * - Tools
     - ``default:pick_mese``
     - :doc:`lt.tool <tool>`
   * - Everything else
     - ``default:stick``, ``default:coal_lump``
     - nowhere else

That last row is why this exists, together with :attr:`player.wielding
<miney.Player.wielding>`: what somebody is holding can be any of the three, so comparing
against it needs one list that has all of them.

.. code-block:: python

    target = player.looking_at
    if target and player.wielding == lt.items.default.torch:
        lt.nodes.set(Node(target.x, target.y + 1, target.z,
                          lt.nodes.names.default.torch))

It is a list and a dictionary as well as a tree of attributes:

    >>> len(lt.items)
    1043
    >>> lt.items["default:stick"]
    'default:stick'
    >>> lt.items.default["stick"]
    'default:stick'
    >>> for name in lt.items.default:
    ...     print(name)

.. tip::

   Use :attr:`lt.nodes.names <miney.Nodes.names>` when you are placing blocks - a name
   from there is one you can actually build with. ``lt.items`` is for reading what
   somebody has.

.. autoclass:: miney.ItemIterable
   :members:
   :inherited-members: object
   :special-members: __getitem__, __iter__, __len__
