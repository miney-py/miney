"""
The main client module for Luanti.
"""
import logging
import time
from hashlib import sha256

from .srp import SRPClient
from .constants import ClientState
from .exceptions import LuantiConnectionError
from .protocol import Protocol
from .command_handler import CommandHandler
from .connection import Connection
from .state import ClientStateHolder


logger = logging.getLogger(__name__)


class LuantiClient:
    """
    The main client class for interacting with a Luanti server.
    It orchestrates connection, state, and command processing.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 30000, playername: str = "Luanti",
                 password: str = "ChangeMe!", lang_code: str = "en", formspec_version: int = 4):
        """
        Initializes the Luanti client.

        :param host: The server host.
        :param port: The server port.
        :param playername: The playername for authentication.
        """
        self.host = host
        self.port = port
        self.playername = playername
        self.password: str = password
        self.lang_code: str = lang_code
        self.formspec_version: int = formspec_version
        self.register_mode: bool = False

        # Core components
        self.state = ClientStateHolder()
        self.protocol = Protocol(
            protocol_id=0x4f457403,
            serialization_version=28,
            protocol_version=39,
            version_string="miney_v1.0"
        )
        # The command handler needs access to the client to trigger actions.
        self.command_handler = CommandHandler(self)
        self.connection = Connection(
            host=self.host,
            port=self.port,
            protocol=self.protocol,
            state=self.state,
            command_processor=self.command_handler.process_command
        )

    def connect(self, register: bool = False) -> bool:
        """
        Connects to the server and authenticates.

        :param register: If True, attempts to register a new user.
        :return: True if connection is successful, False otherwise.
        :raises LuantiConnectionError: If access is denied by the server.
        """
        logger.info(f"Connecting to {self.host}:{self.port} as '{self.playername}'")
        self.register_mode = register

        self.state.reset()
        self.state.state = ClientState.CONNECTING

        if not self.connection.establish():
            self.state.state = ClientState.DISCONNECTED
            return False

        self.send_init()

        # Wait for the connection process to complete
        timeout = time.time() + 15
        while self.state.state < ClientState.JOINED and time.time() < timeout:
            if self.state.access_denied_reason:
                raise LuantiConnectionError(
                    f"Access denied: {self.state.access_denied_reason}",
                    reason_code=self.state.access_denied_code
                )
            time.sleep(0.1)

        if self.state.state < ClientState.JOINED:
            logger.error(f"Connection process timed out in state {self.state.state}")
            self.disconnect()
            return False

        logger.info("Successfully connected and ready for interaction.")

        return True

    def disconnect(self):
        """Disconnects from the server and cleans up resources."""
        self.connection.disconnect()
        self.state.reset()

    def send_packet(self, data: bytes) -> bool:
        """Sends a packet using the connection manager."""
        return self.connection.send_packet(data)

    def send_init(self):
        """Sends the initial INIT command to start authentication."""
        # TODO: We should be able to register a playername with capital letters, but auth fails after registration if we don't use lower().
        username_to_send = self.playername.lower()
        packet_data = self.protocol.create_init_command(username_to_send, self.password)
        logger.debug(f"Sending INIT packet for '{username_to_send}' to start authentication.")
        self.send_packet(packet_data)

    def send_init2(self):
        """Sends the INIT2 command after successful authentication."""
        logger.debug("Sending INIT2 packet...")
        packet_data = self.protocol.create_init2_command()
        if self.send_packet(packet_data):
            self.state.state = ClientState.JOINING
            self.send_client_ready()

    def send_client_ready(self):
        """Sends the CLIENT_READY command."""
        logger.debug("Sending CLIENT_READY packet (lang='%s', formspec_version=%d)...",
                     self.lang_code, self.formspec_version)
        packet_data = self.protocol.create_client_ready_command(self.lang_code, self.formspec_version)
        self.send_packet(packet_data)

    def send_gotblocks(self):
        """Acknowledges receipt of block data (used for node definitions)."""
        logger.debug("Sending GOTBLOCKS for node definitions.")
        packet_data = self.protocol.create_gotblocks_command(0, 0, 0)
        self.send_packet(packet_data)

    def send_chat_message(self, message: str) -> bool:
        """Sends a chat message to the server."""
        if not self.state.authenticated:
            logger.warning("Cannot send chat message: not authenticated.")
            return False
        packet_data = self.protocol.create_chat_message_command(message)
        logger.debug(f"Sending chat message: '{message}'")
        return self.send_packet(packet_data)

    def start_srp_auth(self):
        """Starts the SRP authentication process."""
        logger.debug(f"Starting SRP for user '{self.playername.lower()}'")
        self.state.srp_user = SRPClient(self.playername.lower(), self.password, hash_alg=sha256)
        _, bytes_A = self.state.srp_user.start_authentication()
        cmd = self.protocol.create_srp_bytes_a_command(bytes_A)
        self.send_packet(cmd)
        logger.debug(f"Sent SRP bytes A (len={len(bytes_A)})")

    def send_first_srp(self):
        """Sends a FIRST_SRP packet to register a new user."""
        logger.debug(f"Sending FIRST_SRP for new user '{self.playername}'")
        srp_client = SRPClient(self.playername.lower(), self.password, hash_alg=sha256)
        salt, v_bytes, is_empty = srp_client.generate_first_srp_data()
        packet = self.protocol.create_first_srp_command(salt, v_bytes, is_empty)
        self.send_packet(packet)

    def send_formspec_response(self, formname: str, fields: dict) -> bool:
        """Sends a response to a formspec."""
        if not self.state.authenticated:
            logger.warning("Cannot send formspec response: not authenticated.")
            return False
        packet = self.protocol.create_formspec_response_command(formname, fields)
        logger.debug(f"Sending formspec response for '{formname}'")
        return self.send_packet(packet)

    def _parse_node_definitions(self, data: bytes):
        """
        Parses node definitions. For now, we just store the raw size.
        """
        # TODO: Parse node definitions
        logger.debug("Skipping parsing of node definitions to ensure stability.")
        self.state._node_definitions = {'_raw_size': len(data)}

    def get_access_denied_reason(self, reason_code: int) -> str:
        """Translates an access denied code to a human-readable string."""
        reasons = {
            0: "Invalid password",
            1: "Your client sent something the server didn't expect. Try reconnecting and register your player name!",
            2: "Server is in singleplayer mode.",
            3: "Client version not supported.",
            4: "Player name contains disallowed characters.",
            5: "Player name is not allowed.",
            6: "Server is full.",
            7: "Empty passwords are not allowed.",
            8: "Another client is already connected with this name.",
            9: "Internal server error.",
            10: "Custom reason provided by server.",
            11: "Server is shutting down.",
            12: "Internal server error.",
        }
        return reasons.get(reason_code, f"Unknown reason (code: {reason_code})")

