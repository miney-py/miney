from miney import Minetest


mt = Minetest()

print("Connected to", mt)

players = mt.players
if len(players):
    mt.chat.send_to_all("I'm running the example script...")

    print("Player positions:")
    while True:
        for player in players:
            player = mt.player(player)

            standing_position = player.position
            standing_position["y"] = standing_position["y"] - 1

            print("\r", player.name, player.position, mt.node.get(standing_position), end='')


else:
    raise Exception("There is no player on the server but we need at least one...")
