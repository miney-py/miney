"""
This example shows a simple chatbot, that listens on commands.
"""
from miney import Minetest
import time


mt = Minetest()
mt.lua.run("mineysocket.debug = false")


def miney_command(playername, message):
    print(f"{playername} wrote: {message}")
    mt.chat.send_to_player(playername, f"You've wrote: \"{message}\"")


mt.chat.register_command(name="miney", callback_function=miney_command)

while True:
    mt.receive()
    time.sleep(0.1)

# Todo: receive doesn't react to connection drop
# Todo: On __del__ of chat unregister_chatcommand
