"""
Treasure Hunt Example
=====================

This script demonstrates a simple, interactive treasure hunt game within Luanti
using the Miney library. It showcases several key features:

- **Multiplayer Gameplay:** The game is announced to all players, and anyone can win.
- **Efficient World Interaction:** Uses ranged ``nodes.get`` to quickly scan for the surface.
- **World Modification:** Placing a node (:meth:`~miney.Nodes.set`) to hide the treasure chest.
- **Player Interaction:** Sending global chat messages to all players.
- **Player State:** Reading player positions (:attr:`~miney.Player.position`) to check for a winner.
- **Linear Script Flow:** The script runs from start to finish without threads or callbacks.
- **World Cleanup:** Restores the original blocks when the script ends or is interrupted.

How to Run:
1. Make sure the `miney` mod is installed and enabled on your Luanti server. This game is optimized for the minetest
   game, and there is a very high chance it will not work in other games.
2. Run this script from your terminal, providing connection details if needed:
   python examples/treasure_hunt.py [server] [port] [playername] [password]
3. The game will start immediately for all online players. The first to find the
   chest wins.
"""
import logging
import random
import sys
import time
from typing import Optional, List

from miney import Luanti
from miney.node import Node
from miney.player import Player
from miney.point import Point

# --- Configuration ---
# You can change these values to customize the game
SEARCH_RADIUS: int = 100  # How far from a player the chest can be hidden
SCAN_HEIGHT_START: int = 120  # Y-level to start scanning down from to find the surface
BURY_DEPTH: int = 1  # How many blocks below the surface to bury the chest
WIN_DISTANCE: float = 2.0  # How close a player must be to the chest to win
HINT_INTERVAL: int = 5  # Seconds between hints
ROUND_TIME_LIMIT: int = 300  # 5 minutes in seconds for a round

# --- Logger Setup ---
# Configure a simple logger for script output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def find_surface(lt: Luanti, x: int, z: int) -> Optional[Point]:
    """
    Finds the first non-air block by scanning a column of nodes at once.

    :param lt: The Luanti instance.
    :param x: The X coordinate.
    :param z: The Z coordinate.
    :return: A Point object representing the surface location, or None if no surface is found.
    """
    logger.info(f"Scanning for surface at X={x}, Z={z} from Y={SCAN_HEIGHT_START}.")
    # Define the top and bottom of the column to scan
    p_top = Point(x, SCAN_HEIGHT_START, z)
    p_bottom = Point(x, -30, z)

    try:
        # Get all nodes in the column in a single, efficient call
        nodes_in_column = lt.nodes.get((p_bottom, p_top))

        # Iterate backwards from the top (highest Y) to find the first solid block
        for node in reversed(nodes_in_column):
            if node.name != "air":
                logger.info(f"Surface found at {node.position} with node '{node.name}'.")
                return node.position

        logger.warning(f"No surface found at X={x}, Z={z} (column is all air).")
        return None

    except Exception as e:
        logger.error(f"Error getting node column at ({x}, {z}): {e}")
        return None


def hide_treasure(lt: Luanti, players: List[Player]) -> tuple[Optional[Point], list[Node], Optional[str]]:
    """
    Hides a treasure chest at a random location near a random player.

    :param lt: The Luanti instance.
    :param players: A list of online players to choose from.
    :return: A tuple containing the treasure's Point, a list of original nodes to restore, and the target player's name.
    """
    # Pick a random player to center the search area on
    target_player = random.choice(players)
    start_pos = target_player.position
    logger.info(f"Centering search area on player '{target_player.name}' at {start_pos}.")

    # Try a few times to find a suitable location
    for _ in range(50):  # 10 attempts to find a good spot
        rand_x = start_pos.x + random.randint(-SEARCH_RADIUS, SEARCH_RADIUS)
        rand_z = start_pos.z + random.randint(-SEARCH_RADIUS, SEARCH_RADIUS)

        surface_pos = find_surface(lt, int(rand_x), int(rand_z))

        if surface_pos:
            # The surface_pos from find_surface is already a Node object, so we use it directly.
            surface_node = surface_pos
            # Check for "water" in the node name to exclude water source and flowing water
            if "water" in surface_node.name:
                logger.warning(f"Surface at {surface_pos} is water ('{surface_node.name}'). Retrying.")
                continue

            chest_pos = surface_pos - Point(0, BURY_DEPTH, 0)

            # Get the original nodes before overwriting them
            try:
                # Fetch the column of nodes that will be affected.
                original_blocks = lt.nodes.get([chest_pos, surface_pos])
                # The number of nodes in the column from the surface to the chest is BURY_DEPTH + 1.
                if not (isinstance(original_blocks, list) and len(original_blocks) == BURY_DEPTH + 1):
                    logger.warning(f"Failed to retrieve original nodes. Retrying.")
                    continue
            except Exception as e:
                logger.error(f"Error getting original nodes: {e}")
                continue

            logger.info(f"Hiding treasure chest at {chest_pos}.")

            try:
                # Place a chest with a sign on top for a hint
                lt.nodes.set([
                    Node(chest_pos.x, chest_pos.y, chest_pos.z, name="default:chest"),
                    Node(surface_pos.x, surface_pos.y, surface_pos.z, name="default:mese_post_light_acacia_wood")
                ])

                # Get the chest node object to access its inventory
                chest_node = lt.nodes.get(chest_pos)
                if chest_node:
                    # Create a pool of items to choose from, excluding some non-stackable/undesirable ones
                    item_pool = [
                        item for item in list(lt.nodes.name)
                        if "air" not in item and "water" not in item and "lava" not in item and "ignore" not in item
                    ]
                    # Pick a random item from the pool
                    random_item = random.choice(item_pool)
                    # Add the random item to the chest's inventory
                    chest_node.inventory.add(random_item)
                    logger.info(f"Placed random item '{random_item}' in the treasure chest.")
                else:
                    logger.warning(f"Could not get chest node at {chest_pos} to add item.")

                return chest_pos, original_blocks, target_player.name
            except Exception as e:
                logger.error(f"Failed to place chest at {chest_pos} or add item: {e}")
                # If setting fails, nothing was placed, so no cleanup is needed.
                return None, [], None

    logger.error("Could not find a suitable location to hide the treasure after 10 attempts.")
    return None, [], None


if __name__ == "__main__":
    # --- Connection Details ---
    server = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 30000
    username = sys.argv[3] if len(sys.argv) > 3 else "miney"
    password = sys.argv[4] if len(sys.argv) > 4 else "ChangeThePassword!"

    logger.info(f"Connecting to {server}:{port} as '{username}'...")

    try:
        with Luanti(server, username, password, port) as lt:
            logger.info("Connection successful. Starting treasure hunt loop.")

            lt.player[lt.playername].invisible = True

            while True:  # Main loop to run the game continuously
                original_blocks = []
                try:
                    # 1. Get all online players and filter out the script's own player
                    game_players = [p for p in list(lt.player) if p.name != username]

                    if not game_players:
                        logger.info("No players online. Waiting for players to join...")
                        time.sleep(30)  # Wait before starting a new round
                        continue

                    logger.info(f"Starting a new round with players: {[p.name for p in game_players]}")

                    # 2. Announce the game to everyone
                    lt.chat.send_to_all("A new treasure hunt is starting!")
                    lt.chat.send_to_all(f"A chest is buried {BURY_DEPTH} blocks below the surface.")
                    lt.chat.send_to_all("The first to find it wins. Good luck!")

                    # 3. Hide the treasure and get the original blocks for cleanup
                    treasure_location, original_blocks, target_player_name = hide_treasure(lt, game_players)

                    if not treasure_location:
                        lt.chat.send_to_all("Sorry, I couldn't find a place to hide the treasure. Game cancelled.")
                        time.sleep(30)  # Wait before trying again
                        continue

                    logger.info(f"Treasure hidden at {treasure_location} (target: {target_player_name}). The hunt begins!")

                    round_start_time = time.time()

                    # 4. Main game loop to provide hints and check for a winner
                    winner = None
                    while winner is None:
                        elapsed_time = time.time() - round_start_time
                        if elapsed_time > ROUND_TIME_LIMIT:
                            logger.info("Round time limit exceeded. Ending the round.")
                            lt.chat.send_to_all("Time's up! The treasure was not found.")
                            lt.chat.send_to_all(f"The treasure was at {treasure_location}.")
                            break

                        current_players = [p for p in list(lt.player) if p.name != username]
                        if not current_players:
                            logger.warning("All players have logged out. Ending current round.")
                            break

                        # Check if the target player is still online
                        current_player_names = [p.name for p in current_players]
                        if target_player_name not in current_player_names:
                            logger.warning(f"The target player '{target_player_name}' has left the game. Ending round.")
                            lt.chat.send_to_all(f"The treasure hunt is cancelled because the target player left.")
                            break

                        for player in current_players:
                            try:
                                distance = player.position.distance(treasure_location)
                                if distance < WIN_DISTANCE:
                                    winner = player
                                    break

                                # 5. Construct and send a personalized hint
                                dist_int = int(distance)
                                hint = ""
                                if distance > 100:
                                    hint = f"You are very far from the treasure, about {dist_int} blocks away."
                                elif distance > 50:
                                    hint = f"You're still quite a ways off, around {dist_int} blocks to go."
                                elif distance > 25:
                                    hint = f"You are getting warmer! The treasure is about {dist_int} blocks from here."
                                elif distance > 10:
                                    hint = f"You're hot on the trail! Only {dist_int} blocks now."
                                else:
                                    hint = f"You are extremely close! Less than {dist_int + 1} blocks away!"

                                lt.chat.send_to_player(player.name, hint)
                            except Exception as e:
                                logger.warning(f"Could not process player {player.name}: {e}")

                        if winner:
                            break
                        time.sleep(HINT_INTERVAL)

                    # 6. Announce winner and give them time to loot
                    if winner:
                        lt.chat.send_to_all(f"★★ {winner.name} found the treasure! Congratulations! ★★")
                        logger.info(f"Winner found: {winner.name}")

                        # Announce the contents of the chest
                        chest_node = lt.nodes.get(treasure_location)
                        if chest_node:
                            try:
                                chest_contents = chest_node.inventory.get_list("main")
                                # Filter out empty slots (None) and create a list of item strings
                                non_empty_items = [item for item in chest_contents if item]
                                if non_empty_items:
                                    lt.chat.send_to_all(f"The chest contained: {', '.join(non_empty_items)}")
                                else:
                                    lt.chat.send_to_all("The chest was empty!")
                            except Exception as e:
                                logger.warning(f"Could not read chest inventory: {e}")

                        lt.chat.send_to_all("The chest will be removed in 30 seconds. A new round will begin shortly.")
                        time.sleep(30)
                    else:
                        lt.chat.send_to_all("The round has ended.")
                        time.sleep(10)  # Short pause before next round check

                finally:
                    # This block runs at the end of each round
                    if original_blocks:
                        logger.info("Restoring original blocks to clean up the world...")
                        try:
                            lt.nodes.set(original_blocks)
                            logger.info("World restored successfully.")
                        except Exception as e:
                            logger.error(f"Failed to restore world state: {e}")

    except KeyboardInterrupt:
        logger.info("Script stopped by user.")
    except Exception as e:
        logger.critical(f"A critical error occurred: {e}", exc_info=True)
    finally:
        logger.info("Script shutting down.")
