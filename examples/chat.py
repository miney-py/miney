import logging
import signal
import sys
import time

from miney.luanti import Luanti

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

    def on_chat_message(event: dict) -> None:
        payload = event.get("payload") or {}
        name = payload.get("name")
        msg = payload.get("message")
        logger.info("chat_message from %s: %s", name, msg)

    # Subscribe to chat messages (non-blocking dispatch thread delivers events)
    lt.chat.on_message(on_chat_message)

    # Register a simple chat command handled in Python
    def hello_cmd(event: dict) -> None:
        payload = event.get("payload") or {}
        issuer = payload.get("issuer")
        lt.chat.send_to_player(issuer, "Hi from Miney Python callbacks! 👋")

    lt.chat.register_command("hello", hello_cmd)

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
        try:
            lt.chat.off_message(on_chat_message)
        except Exception as e:
            logger.error("Error deactivating subscription: %s", e)
        lt.disconnect()
        logger.info("Shut down cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
