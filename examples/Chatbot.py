"""
This example shows a simple chatbot, that listens on commands but also on any messages.
"""
from miney import Minetest
import logging


logging.basicConfig(level=logging.DEBUG)

mt = Minetest()
mt.lua.run("mineysocket.debug = true")


def mycommand(*args):
    print(args)


# print(mt.chat.send_to_all("all"))
# print(mt.chat.send_to_player("Miney", "Miney"))

mt.chat.register_command(name="miney", callback_function=mycommand)

while True:
    mt.receive(timeout=False)
