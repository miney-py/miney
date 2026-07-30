from .nodes import NameIterable


class ItemIterable(NameIterable):
    """
    Every name that can be in a player's hand, as attributes you can find with TAB.

    ``lt.items.default.stick`` is the string ``'default:stick'``. Luanti calls all of it
    *items*, and it is the three lists Miney otherwise keeps apart in one place:

    * blocks, which are also :attr:`lt.nodes.names <miney.Nodes.names>`
    * tools, which are also :attr:`lt.tool <miney.Luanti.tool>`
    * everything else - sticks, coal, apples, ingots - which is only here

    That is why it exists: :attr:`player.wielding <miney.Player.wielding>` can answer
    with any of the three, so comparing against it needs one list that has all of them::

        >>> if player.wielding == lt.items.default.stick:
        ...     lt.chat.send_to_all("A stick! Careful.")

    Everything :class:`~miney.nodes.NameIterable` can do, this can do. You do not create
    it yourself, it is :attr:`lt.items <miney.Luanti.items>`.
    """

    def __repr__(self):
        return f"<Luanti items: {len(self)}>"
