from typing import TYPE_CHECKING
from .player import Player
if TYPE_CHECKING:
    from .luanti import Luanti


class Inventory:
    """
    Inventories are places to store items, like Chests or player inventories.

    You do not create this yourself - you get one from
    :attr:`~miney.Player.inventory` or :attr:`~miney.node.Node.inventory`.
    """

    def __init__(self, luanti: 'Luanti', parent: object):
        self.lt = luanti
        self.parent = parent

    def _no_owner(self, action: str) -> TypeError:
        """
        Build the error for an inventory that belongs to neither a player nor a node.

        Every method here has to ask what it is attached to, because the Lua call
        differs. Without this they returned ``None`` or ``[]`` for anything else, so a
        wrongly built Inventory looked like an empty one.

        :param action: What was attempted, for the message.
        :return: The exception to raise.
        """
        return TypeError(
            f"Cannot {action}: this inventory belongs to a "
            f"{type(self.parent).__name__}, and only players and nodes have one. Get "
            f"an inventory from lt.players['Name'].inventory or from "
            f"lt.nodes.get(point).inventory."
        )

    def _getter(self, action: str) -> str:
        """
        Build the Lua that fetches this inventory, whoever it belongs to.

        A player inventory is found by name and a node inventory by position, so every
        method here needs the same two-way decision. It lives in one place so it is
        also quoted in one place: the player name goes through
        :meth:`~miney.Lua.dumps` rather than into the Lua source as-is.

        :param action: What was attempted, for the error message.
        :return: A Lua expression evaluating to the inventory, or ``nil``.
        :raises TypeError: If this inventory belongs to neither a player nor a node.
        """
        from .node import Node
        if isinstance(self.parent, Player):
            spec = {"type": "player", "name": self.parent.name}
        elif isinstance(self.parent, Node):
            spec = {"type": "node",
                    "pos": {"x": self.parent.x, "y": self.parent.y, "z": self.parent.z}}
        else:
            raise self._no_owner(action)
        return f"minetest.get_inventory({self.lt.lua.dumps(spec)})"

    def add(self, item: str, amount: int = 1) -> None:
        """
        Add an item to an inventory. Possible items can be obtained from :attr:`~miney.Nodes.names`.

        :param item: item type
        :param amount: item amount
        :return: None
        :raises TypeError: If this inventory belongs to neither a player nor a node
        """
        getter = self._getter(f"add {amount}x '{item}'")
        self.lt.lua.run(
            f'local inv = {getter}\n'
            f'if inv then\n'
            f'    inv:add_item("main", ItemStack({self.lt.lua.dumps(f"{item} {amount}")}))\n'
            f'end',
            wait=False,
        )

    def remove(self, item: str, amount: int = 1) -> None:
        """
        Remove an item from an inventory. Possible items can be obtained from lt.nodes.names.

        :param item: item type
        :param amount: item amount
        :return: None
        :raises TypeError: If this inventory belongs to neither a player nor a node
        """
        getter = self._getter(f"remove {amount}x '{item}'")
        self.lt.lua.run(
            f'local inv = {getter}\n'
            f'if inv then\n'
            f'    inv:remove_item("main", ItemStack({self.lt.lua.dumps(f"{item} {amount}")}))\n'
            f'end',
            wait=False,
        )

    def get_lists(self) -> list[str]:
        """
        Get the names of all available inventory lists.

        :return: A list of inventory list names (e.g., ["main", "craft"]), empty if
            there are none.
        :raises TypeError: If this inventory belongs to neither a player nor a node
        """
        getter = self._getter("list the inventory lists")
        # `or []`: an empty Lua table arrives as None, and a caller looping over the
        # answer should not have to know that.
        return self.lt.lua.run(f"""
            local inv = {getter}
            if not inv then return {{}} end
            local lists = inv:get_lists()
            if not lists then return {{}} end
            local names = {{}}
            for name, _ in pairs(lists) do
                table.insert(names, name)
            end
            return names
        """) or []

    def get_list(self, name: str = "main") -> list[str]:
        """
        Get the content of an inventory list.

        Only the occupied slots come back, as strings like ``"mcl_core:apple 5"`` - the
        empty ones are left out rather than filling the answer with placeholders.

        :param name: The name of the list to get (e.g., "main").
        :return: A list of item strings, empty if the inventory list is.
        :raises TypeError: If this inventory belongs to neither a player nor a node
        """
        getter = self._getter(f"read the inventory list '{name}'")
        # `or []`: an empty Lua table arrives as None, and an empty chest is normal.
        return self.lt.lua.run(f"""
            local inv = {getter}
            if not inv then return {{}} end
            local list = inv:get_list({self.lt.lua.dumps(name)})
            if not list then return {{}} end
            local out = {{}}
            for _, stack in ipairs(list) do
                if not stack:is_empty() then
                    table.insert(out, stack:to_string())
                end
            end
            return out
        """) or []
