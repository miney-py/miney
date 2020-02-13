import miney


class Inventory:
    """
    Inventories are places to store items, like Chests or player inventories.
    """

    def __init__(self, minetest: miney.Minetest, parent: object):
        self.mt = minetest
        self.parent = parent

    def add(self, item: str, amount: int = 1) -> None:
        """
        Add an item to an inventory. Possible items can be obtained from :attr:`~miney.Node.type`.

        :param item: item type
        :param amount: item amount
        :return: None
        """
        if isinstance(self.parent, miney.Player):
            self.mt.lua.run(
                f"minetest.get_inventory("
                f"{{type = \"player\", name = \"{self.parent.name}\"}}"
                f"):add_item(\"main\", ItemStack(\"{item} {amount}\"))"
            )

    def remove(self, item: str, amount: int = 1) -> None:
        """
        Remove an item from an inventory. Possible items can be obtained from mt.node.type.

        :param item: item type
        :param amount: item amount
        :return: None
        """
        if isinstance(self.parent, miney.Player):
            self.mt.lua.run(
                f"minetest.get_inventory({{type = \"player\", "
                f"name = \"{self.parent.name}\"}}):remove_item(\"main\", ItemStack(\"{item} {amount}\"))")
