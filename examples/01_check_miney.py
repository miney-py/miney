from miney import Luanti

# Using a 'with' statement ensures that the connection is properly closed
# when the block is exited, preventing shutdown errors.
with Luanti() as lt:
    # Without any parameters `Luanti()` will connect to 127.0.0.1:30000 with the player name "miney".
    # If the user isn't registered, it will create an account with the password "ChangeThePassword!" and log in with that account.

    print("Connected to", lt)

    lt.chat.send_to_all("Luanti works!")

    players = lt.player

    if len(players):

        print("Players positions:")

        for player in players:
            standing_position = player.position
            print(player.name, player.position, player.look_horizontal, player.look_vertical, lt.nodes.get(standing_position))

