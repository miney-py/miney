class ToolIterable:
    """Tool type, implemented as iterable for easy autocomplete in the interactive shell"""
    def __init__(self, parent, tool_types=None):

        self.__parent = parent

        if tool_types:

            # get type categories list
            type_categories = {}
            for ntype in tool_types:
                if ":" in ntype:
                    type_categories[ntype.split(":")[0]] = ntype.split(":")[0]
            for tc in dict.fromkeys(type_categories):
                self.__setattr__(tc, ToolIterable(parent))

            # values to categories
            for ttype in tool_types:
                if ":" in ttype:
                    self.__getattribute__(ttype.split(":")[0]).__setattr__(ttype.split(":")[1], ttype)
                else:
                    self.__setattr__(ttype, ttype)  # for 'air' and 'ignore'

    def __iter__(self):
        # todo: list(mt.node.tool.default) should return only default group
        return iter(self.__parent._tools_cache)

    def __getitem__(self, item_key):
        if item_key in self.__parent.node_types:
            return item_key
        else:
            if type(item_key) == int:
                return self.__parent.node_types[item_key]
            raise IndexError("unknown node type")

    def __len__(self):
        return len(self.__parent._tools_cache)
