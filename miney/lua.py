import re
import string
from random import choices
import miney


class Lua:
    """
    Lua specific functions.
    """
    def __init__(self, mt: miney.Minetest):
        self.mt = mt

    def run(self, lua_code: str):
        """
        Run load code on the minetest server.

        :param lua_code: lua code to run
        :return: The return value. Multiple values as a list.
        """
        # generates nearly unique id's (under 1000 collisions in 10 million values)
        result_id = ''.join(choices(string.ascii_lowercase + string.ascii_uppercase + string.digits, k=6))

        self.mt.send({"lua": lua_code, "id": result_id})

        try:
            return self.mt.receive(result_id)
        except miney.SessionReconnected:
            # We rerun the code, cause he was dropped during reconnect
            return self.run(lua_code)

    def dumps(self, data) -> str:
        """
        Convert python data types to a string with lua data types.

        :param data: Python data
        :return: Lua data
        """
        # credits:
        # https://stackoverflow.com/questions/54392760/serialize-a-dict-as-lua-table/54392761#54392761
        if type(data) is str:
            return '"{}"'.format(re.escape(data))
        if type(data) in (int, float):
            return '{}'.format(data)
        if type(data) is bool:
            return data and "true" or "false"
        if type(data) is list:
            l = "{"
            l += ", ".join([self.dumps(item) for item in data])
            l += "}"
            return l
        if type(data) is dict:
            t = "{"
            t += ", ".join(
                [
                    '[\"{}\"]={}'.format(re.escape(k), self.dumps(v)) for k, v in data.items()
                ]
            )
            t += "}"
            return t
        raise ValueError("Unknown type {}".format(type(data)))