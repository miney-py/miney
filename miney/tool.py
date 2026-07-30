from .nodes import NameIterable


class ToolIterable(NameIterable):
    """
    Tool names, as attributes you can find with TAB.

    ``lt.tool.default.pick_mese`` is the string ``'default:pick_mese'``. Only things a
    player swings are in here - :attr:`lt.items <miney.Luanti.items>` is the list of
    everything that can be in a hand, tools included.

    Everything :class:`~miney.nodes.NameIterable` can do, this can do. You do not create
    it yourself, it is :attr:`lt.tool <miney.Luanti.tool>`.
    """

    def __repr__(self):
        return f"<Luanti tools: {len(self)}>"
