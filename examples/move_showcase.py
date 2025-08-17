import logging
import math
import random
import time

from miney import Luanti, Point, Player

# Configure logger for the example
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(module)s.%(funcName)s | %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


def print_welcome():
    """
    Prints a welcome message to the console.
    """
    print("=" * 50)
    print("Miney Move Showcase")
    print("=" * 50)
    print("This script demonstrates the player movement capabilities.")
    print("Please make sure a player named 'miney' is online.")
    print("You can watch this player in the game to see the movements.")
    print("-" * 50)


def showcase_moves(player: Player):
    """
    Demonstrates various movement capabilities of the Player.move() method.

    :param player: The player object to control.
    """
    print("\nStarting move showcase...")
    logger.info(f"Controlling player: {player.name}")

    # Store initial state to restore it later
    initial_pos = player.position
    initial_noclip = player.noclip
    logger.info(f"Initial position: {initial_pos}")

    try:
        # Enable noclip for smooth air movement, otherwise the player would fall
        player.noclip = True
        time.sleep(0.5)  # Give the server a moment to apply the setting

        # 1. Simple move to a new position
        print("\n1. Moving 10 blocks forward (smoothly).")
        target_pos = initial_pos + Point(10, 0, 0)
        player.move(destination=target_pos, smooth=True, duration=2)
        time.sleep(2.5)  # Wait for the movement to complete

        # 2. Move back to start while looking at the previous target
        print("\n2. Moving back to start while looking at the last position.")
        player.move(destination=initial_pos, look_at=target_pos, smooth=True, duration=2)
        time.sleep(2.5)

        # 3. Circle movement
        print("\n3. Performing a circular flight pattern.")
        radius = 8
        steps = 40
        # The center of the circle is in front of the player's starting position
        center = player.position + Point(radius, 0, 0)
        for i in range(steps + 1):
            # Calculate the next point on the circle
            angle = (i / steps) * 2 * math.pi
            x = center.x - radius * math.cos(angle)
            z = center.z + radius * math.sin(angle)
            y = initial_pos.y + 3  # Fly a bit above the ground

            # The player will always look at the center of the circle
            player.move(
                destination=Point(x, y, z),
                look_at=center,
                smooth=True,
                duration=0.2
            )
            time.sleep(0.2)

        # 4. "Dance" routine with random movements
        print("\n4. Let's dance! Performing some random moves.")
        for i in range(10):
            # Random offset from the starting position
            offset = Point(
                random.uniform(-3, 3),
                random.uniform(0, 2),
                random.uniform(-3, 3)
            )
            # Random point to look at
            look_offset = Point(
                random.uniform(-10, 10),
                random.uniform(-5, 5),
                random.uniform(-10, 10)
            )
            player.move(
                destination=initial_pos + offset,
                look_at=initial_pos + look_offset,
                smooth=True,
                duration=0.4
            )
            time.sleep(0.5)

        print("\nShowcase finished!")

    finally:
        # Clean up: move back to the starting point and reset noclip
        print("\nReturning to initial position and restoring state.")
        player.move(destination=initial_pos, smooth=True, duration=1.5)
        time.sleep(2)
        player.noclip = initial_noclip
        logger.info("Player state restored.")


def main():
    """
    Main function to run the move showcase.
    """
    print_welcome()

    try:
        with Luanti() as lt:
            # For this example, we control the 'miney' player
            player_name = "miney"
            try:
                player = lt.players[player_name]
            except KeyError:
                logger.error(f"Player '{player_name}' not found on the server.")
                return

            if not player.is_online:
                logger.error(f"Player '{player_name}' is not online. Please log in and try again.")
                return

            showcase_moves(player)

    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)


if __name__ == "__main__":
    main()
