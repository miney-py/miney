import logging
import signal
import sys
import time

from miney.luanti import Luanti

# Import specific event classes
from miney.events import (
    ChatCommandEvent,
    ChatMessageEvent,
    PlayerJoinsEvent,
    PlayerLeavesEvent,
)

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(module)s.%(funcName)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)


def main() -> int:
    setup_logging()
    logger.info("Starting non-blocking callbacks example")

    lt = Luanti(server="127.0.0.1", playername="miney", password="ChangeThePassword!", port=30000)

    # Use the flattened event attributes
    @lt.chat.on(event="chat_message")
    def on_chat_message(event: ChatMessageEvent) -> None:
        logger.info("chat_message from %s: %s", event.sender_name, event.message)

    # Register a handler for players leaving the game
    @lt.callbacks.on("player_leaves")
    def on_player_leaves(event: PlayerLeavesEvent) -> None:
        reason = "timed out" if event.timed_out else "disconnected"
        logger.info("Player %s has left the game (%s).", event.player_name, reason)

    # Register a handler for players joining the game
    @lt.callbacks.on("player_joins")
    def on_player_joins(event: PlayerJoinsEvent) -> None:
        player_name = event.player_name
        # The payload contains the name; get the full Player object via the players list
        player_obj = lt.players[player_name]

        if event.last_login:
            # Format the datetime object for logging
            last_login_str = event.last_login.strftime('%Y-%m-%d %H:%M:%S')
            logger.info("Player %s just joined. Last login was at %s.", player_name, last_login_str)
            lt.chat.send_to_player(player_obj, f"Welcome back, {player_name}!")
        else:
            logger.info("New player %s just joined for the first time!", player_name)
            lt.chat.send_to_player(player_obj, f"Welcome to the server, {player_name}!")

    # Register a simple chat command handled in Python using the decorator
    @lt.chat.command("hello", description="Says hi back to the issuer.")
    def hello_cmd(event: ChatCommandEvent) -> None:
        logger.info(f"Received /hello command from {event.issuer}, {event.param}")
        lt.chat.send_to_player(event.issuer, "Hi from Miney Python callbacks! 👋")

    # It's also possible to register and unregister callbacks procedurally
    def procedural_chat_handler(event: ChatMessageEvent) -> None:
        # We only want to log messages from a specific player, for example 'singleplayer'
        if event.sender_name == "singleplayer":
            logger.info(
                "(Procedural handler) singleplayer said: %s", event.message
            )

    lt.on_event("chat_message", procedural_chat_handler)

    stop = False

    def handle_sigint(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        logger.info("Press Ctrl+C to exit. Try typing '/hello' in-game.")
        while not stop:
            time.sleep(0.2)
    finally:
        # The disconnect method handles unregistering all callbacks and commands automatically.
        lt.disconnect()
        logger.info("Shut down cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
