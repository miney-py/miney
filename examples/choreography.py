"""
A multi-client choreography example.

This script demonstrates how to connect multiple clients to a Minetest server
and have them perform a synchronized dance routine. It uses Python's
threading module to simulate multiple clients, each running in its own thread.

The choreography consists of two main parts:
1. All dancers line up in a row.
2. They perform a synchronized circular flight pattern, always looking towards
   the center of the circle.
"""
import logging
import math
import threading
import time
from typing import List

from miney import Luanti, Point

# --- Configuration ---
NUM_DANCERS = 4
SERVER = "127.0.0.1"
PASSWORD = "ChangeThis"
BASE_PLAYER_NAME = "dancer"

# --- Choreography Parameters ---
# Center of the entire solar system, and the point the "planet" orbits
SYSTEM_CENTER = Point(0, 20, 0)

# Planet (the first dancer, index 0) parameters
PLANET_ORBIT_RADIUS = 15.0
PLANET_ORBIT_SPEED_MULTIPLIER = 1.0  # Revolutions per full animation cycle

# Moon (other dancers) parameters
MOON_BASE_ORBIT_RADIUS = 4.0
MOON_RADIUS_INCREMENT = 2.0
MOON_ORBIT_SPEED_MULTIPLIER = 12.0  # Moons orbit the planet faster

# General animation parameters
TOTAL_STEPS = 240  # Total number of animation steps for one full planet orbit
STEP_DURATION = 0.2  # Duration of each small step in seconds

# Synchronization primitive to make all dancers start the main routine together.
# We need NUM_DANCERS + 1 parties: one for each dancer and one for the main thread.
barrier = threading.Barrier(NUM_DANCERS + 1)

# --- Logging Setup ---
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(threadName)-12s | %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)


def dance_routine(player_name: str, dancer_index: int):
    """
    The routine each dancer will perform.

    This function simulates a small solar system:
    - Dancer 0 is the "planet," orbiting a central point.
    - Other dancers are "moons," orbiting the planet.

    :param player_name: The name of the player for this client.
    :param dancer_index: The index of the dancer (0 for planet, >0 for moons).
    """
    logger.info("Connecting to the server...")
    initial_noclip_state = False

    try:
        with Luanti(server=SERVER, playername=player_name, password=PASSWORD) as m:
            player = m.players[player_name]
            initial_noclip_state = player.noclip

            # --- Phase 1: Move to initial position ---
            logger.info("Moving to initial position in the formation.")
            player.noclip = True
            time.sleep(0.2)  # Give noclip time to apply

            # Calculate initial positions (at step i=0)
            planet_pos_initial = SYSTEM_CENTER + Point(PLANET_ORBIT_RADIUS, 0, 0)
            my_initial_pos: Point

            if dancer_index == 0:  # I am the planet
                my_initial_pos = planet_pos_initial
            else:  # I am a moon
                moon_index = dancer_index - 1
                num_moons = NUM_DANCERS - 1 if NUM_DANCERS > 1 else 1

                moon_phase_offset = (moon_index / num_moons) * 2 * math.pi
                my_moon_radius = MOON_BASE_ORBIT_RADIUS + (moon_index * MOON_RADIUS_INCREMENT)

                moon_orbit_offset = Point(
                    my_moon_radius * math.cos(moon_phase_offset),
                    0,
                    my_moon_radius * math.sin(moon_phase_offset)
                )
                my_initial_pos = planet_pos_initial + moon_orbit_offset

            player.move(destination=my_initial_pos, duration=3, smooth=True)
            time.sleep(3.5)  # Wait for movement

            logger.info("In position. Waiting for other dancers.")
            barrier.wait()

            # --- Phase 2: Planetary Dance ---
            logger.info("Starting planetary dance routine.")
            last_moon_yaw = None  # For unwrapping the moon's yaw angle to prevent spinning

            for i in range(1, TOTAL_STEPS + 1):
                # Everyone calculates the planet's position for this step
                planet_angle = (i / TOTAL_STEPS) * 2 * math.pi * PLANET_ORBIT_SPEED_MULTIPLIER
                planet_pos = SYSTEM_CENTER + Point(
                    PLANET_ORBIT_RADIUS * math.cos(planet_angle),
                    0,
                    PLANET_ORBIT_RADIUS * math.sin(planet_angle)
                )

                my_target_pos: Point
                move_kwargs = {
                    "smooth": True,
                    "duration": STEP_DURATION
                }

                if dancer_index == 0:  # I am the planet
                    my_target_pos = planet_pos
                    move_kwargs["look_at"] = SYSTEM_CENTER
                else:  # I am a moon
                    moon_index = dancer_index - 1
                    num_moons = NUM_DANCERS - 1 if NUM_DANCERS > 1 else 1

                    moon_angle = (i / TOTAL_STEPS) * 2 * math.pi * MOON_ORBIT_SPEED_MULTIPLIER
                    moon_phase_offset = (moon_index / num_moons) * 2 * math.pi
                    final_moon_angle = moon_angle + moon_phase_offset

                    my_moon_radius = MOON_BASE_ORBIT_RADIUS + (moon_index * MOON_RADIUS_INCREMENT)

                    moon_orbit_offset = Point(
                        my_moon_radius * math.cos(final_moon_angle),
                        0,
                        my_moon_radius * math.sin(final_moon_angle)
                    )
                    my_target_pos = planet_pos + moon_orbit_offset

                    # To prevent spinning, we calculate yaw manually and unwrap it.
                    # The direction to look is from the moon to the planet (-moon_orbit_offset).
                    direction_to_planet = -moon_orbit_offset
                    current_yaw = math.atan2(direction_to_planet.x, direction_to_planet.z)

                    # Unwrap the angle to ensure the shortest rotation path.
                    if last_moon_yaw is not None:
                        while current_yaw - last_moon_yaw > math.pi:
                            current_yaw -= 2 * math.pi
                        while current_yaw - last_moon_yaw < -math.pi:
                            current_yaw += 2 * math.pi

                    move_kwargs["yaw"] = current_yaw
                    last_moon_yaw = current_yaw

                player.move(destination=my_target_pos, **move_kwargs)
                time.sleep(STEP_DURATION)

            logger.info("Finished dancing.")

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
    finally:
        # --- Cleanup ---
        try:
            # Use a new connection for cleanup if the main one failed
            with Luanti(server=SERVER, playername=player_name, password=PASSWORD) as m:
                player = m.players[player_name]
                logger.info("Restoring noclip state.")
                player.noclip = initial_noclip_state
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")

        logger.info("Disconnecting.")


def main():
    """
    Main function to set up and run the choreography.
    """
    print("--- Multi-Client Choreography Showcase: Solar System ---")
    print(f"Starting {NUM_DANCERS} dancers (1 planet, {NUM_DANCERS - 1} moons)...")
    print("Make sure the Minetest server is running and accessible.")
    print(f"Dancers will connect with names '{BASE_PLAYER_NAME}_1' to '{BASE_PLAYER_NAME}_{NUM_DANCERS}'.")
    print("On first connection, you may need to grant them 'miney' and 'noclip' privileges.")
    print("------------------------------------------")

    threads: List[threading.Thread] = []
    for i in range(NUM_DANCERS):
        player_name = f"{BASE_PLAYER_NAME}_{i + 1}"
        thread = threading.Thread(
            target=dance_routine, args=(player_name, i), name=player_name
        )
        threads.append(thread)
        thread.start()
        time.sleep(0.2)  # Stagger connections

    try:
        logger.info("Main thread waiting for all dancers to get in position...")
        barrier.wait(timeout=60)
        logger.info("All dancers are ready! The show begins now.")
    except threading.BrokenBarrierError:
        logger.error("Not all dancers reached their position in time. Aborting.")
        return

    for thread in threads:
        thread.join()

    logger.info("Choreography showcase finished.")


if __name__ == "__main__":
    main()
