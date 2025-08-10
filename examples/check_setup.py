"""
Miney Setup Checker
===================

This script connects to a Luanti server to verify that both the server and
the Miney library are correctly configured. It gathers and displays key
information, such as the server version, online players, and the number of
registered nodes and tools.

This is the recommended first script to run after installing Miney to ensure
your environment is ready.

How to Run:
1. Make sure the `miney` mod is installed and enabled on your Luanti server.
2. Run this script from your terminal, providing connection details if needed:
   python examples/check_setup.py [server] [port] [playername] [password]
"""
import logging
import sys

from miney import Luanti, LuantiConnectionError

# --- Logger Setup ---
# Configure a simple logger for clean and informative output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    # --- Connection Details ---
    server = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 30000
    username = sys.argv[3] if len(sys.argv) > 3 else "miney"
    password = sys.argv[4] if len(sys.argv) > 4 else "ChangeThePassword!"

    logger.info(f"Attempting to connect to {server}:{port} as '{username}'...")

    try:
        # Use a 'with' statement for automatic connection management
        with Luanti(server=server, playername=username, password=password, port=port) as lt:
            logger.info("Connection successful!")
            print("-" * 40)
            logger.info("--- Luanti & Miney Setup Check ---")

            # 1. Get Server Information
            server_version = lt.version
            logger.info(f"Luanti Server Version: {server_version}")

            # 2. Get Player Information
            players = list(lt.players)
            player_count = len(players)
            player_names = ", ".join([p.name for p in players]) if players else "None"
            logger.info(f"Players Online ({player_count}): {player_names}")

            # 3. Get World Content Information
            # This confirms that Miney can access the game's content database
            node_count = len(list(lt.nodes.name))
            tool_count = len(list(lt.tool))
            logger.info(f"Registered Node Types: {node_count}")
            logger.info(f"Registered Tool Types: {tool_count}")

            print("-" * 40)

            # 4. Final Verification
            if node_count > 10 and tool_count > 0:
                logger.info("✅ Verification successful. Miney appears to be correctly set up!")
            else:
                logger.warning("⚠️ Verification complete, but with warnings.")
                logger.warning("Low node/tool count may indicate an issue with the server or mod.")

    except LuantiConnectionError as e:
        logger.critical(f"❌ Connection Failed: {e}")
        logger.critical("Please check the following:")
        logger.critical("  - Is the Luanti server running?")
        logger.critical("  - Are the server address and port correct?")
        logger.critical("  - Is the 'miney' mod installed and enabled on the server?")
        logger.critical("  - Is the password correct?")
    except KeyboardInterrupt:
        logger.info("\nScript interrupted by user.")
    except Exception as e:
        logger.critical(f"An unexpected error occurred: {e}", exc_info=True)
    finally:
        logger.info("Script finished.")
