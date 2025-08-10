from typing import TYPE_CHECKING
from .player import Player
if TYPE_CHECKING:
    from .luanti import Luanti


class Inventory:
    """
    Inventories are places to store items, like Chests or player inventories.
    """

    def __init__(self, luanti: 'Luanti', parent: object):
        self.lt = luanti
        self.parent = parent

    def add(self, item: str, amount: int = 1) -> None:
        """
        Add an item to an inventory. Possible items can be obtained from :attr:`~miney.Nodes.type`.

        :param item: item type
        :param amount: item amount
        :return: None
        """
        from .node import Node
        if isinstance(self.parent, Player):
            self.lt.lua.run(
                f"minetest.get_inventory("
                f"{{type = \"player\", name = \"{self.parent.name}\"}}"
                f"):add_item(\"main\", ItemStack(\"{item} {amount}\"))"
            )
        elif isinstance(self.parent, Node):
            pos_str = f"{{x={self.parent.x}, y={self.parent.y}, z={self.parent.z}}}"
            self.lt.lua.run(
                f'local pos = {pos_str}\n'
                f'local inv = minetest.get_inventory({{type = "node", pos = pos}})\n'
                f'if inv then\n'
                f'    local list_name = "main"\n'
                f'    local lists = inv:get_lists()\n'
                f'    if lists and #lists > 0 then\n'
                f'        list_name = lists[1]\n'
                f'    end\n'
                f'    inv:add_item(list_name, ItemStack("{item} {amount}"))\n'
                f'end'
            )

    def remove(self, item: str, amount: int = 1) -> None:
        """
        Remove an item from an inventory. Possible items can be obtained from lt.nodes.names.

        :param item: item type
        :param amount: item amount
        :return: None
        """
        from .node import Node
        if isinstance(self.parent, Player):
            self.lt.lua.run(
                f"minetest.get_inventory({{type = \"player\", "
                f"name = \"{self.parent.name}\"}}):remove_item(\"main\", ItemStack(\"{item} {amount}\"))")
        elif isinstance(self.parent, Node):
            pos_str = f"{{x={self.parent.x}, y={self.parent.y}, z={self.parent.z}}}"
            self.lt.lua.run(
                f'local pos = {pos_str}\n'
                f'local inv = minetest.get_inventory({{type = "node", pos = pos}})\n'
                f'if inv then\n'
                f'    inv:remove_item("main", ItemStack("{item} {amount}"))\n'
                f'end'
            )

    def get_lists(self) -> list[str]:
        """
        Get the names of all available inventory lists.

        :return: A list of inventory list names (e.g., ["main", "craft"]).
        """
        lua_code = """
            local inv = {getter}
            if not inv then return {{}} end
            local lists = inv:get_lists()
            if not lists then return {{}} end
            local names = {{}}
            for name, _ in pairs(lists) do
                table.insert(names, name)
            end
            return names
        """
        from .node import Node
        if isinstance(self.parent, Player):
            getter = f'minetest.get_inventory({{type = "player", name = "{self.parent.name}"}})'
            return self.lt.lua.run(lua_code.format(getter=getter))
        elif isinstance(self.parent, Node):
            pos_str = f"{{x={self.parent.x}, y={self.parent.y}, z={self.parent.z}}}"
            getter = f'minetest.get_inventory({{type = "node", pos = {pos_str}}})'
            return self.lt.lua.run(lua_code.format(getter=getter))
        return []

    def get_list(self, name: str = "main") -> list[str | None]:
        """
        Get the content of an inventory list.

        :param name: The name of the list to get (e.g., "main").
        :return: A list of item strings. Empty slots are represented by None.
        """
        lua_code = """
            local inv = {getter}
            if not inv then return {{}} end
            local list = inv:get_list("{list_name}")
            if not list then return {{}} end
            local out = {{}}
            for _, stack in ipairs(list) do
                if not stack:is_empty() then
                    table.insert(out, stack:to_string())
                else
                    table.insert(out, nil)
                end
            end
            return out
        """
        from .node import Node
        if isinstance(self.parent, Player):
            getter = f'minetest.get_inventory({{type = "player", name = "{self.parent.name}"}})'
            return self.lt.lua.run(lua_code.format(getter=getter, list_name=name))
        elif isinstance(self.parent, Node):
            pos_str = f"{{x={self.parent.x}, y={self.parent.y}, z={self.parent.z}}}"
            getter = f'minetest.get_inventory({{type = "node", pos = {pos_str}}})'
            return self.lt.lua.run(lua_code.format(getter=getter, list_name=name))
        return []
