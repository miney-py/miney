"""
Handles processing of commands received from the server.
"""
import io
import logging
import re
import struct
import zlib
from typing import TYPE_CHECKING, Callable

from .constants import ClientState, ToClientCommand
from .exceptions import LuantiConnectionError

if TYPE_CHECKING:
    from .client import LuantiClient

logger = logging.getLogger(__name__)


class CommandHandler:
    """
    Processes commands from the server and updates the client state accordingly.
    """

    def __init__(self, client: 'LuantiClient'):
        """
        Initializes the CommandHandler.

        :param client: The LuantiClient instance.
        """
        self.client = client
        self.handlers = {
            ToClientCommand.HELLO: self._handle_hello,
            ToClientCommand.AUTH_ACCEPT: self._handle_auth_accept,
            ToClientCommand.ACCESS_DENIED: self._handle_access_denied,
            ToClientCommand.SRP_BYTES_S_B: self._handle_srp_bytes_s_b,
            ToClientCommand.NODEDEF: self._handle_nodedef,
            ToClientCommand.SHOW_FORMSPEC: self._handle_show_formspec,
            ToClientCommand.CHAT_MESSAGE: self._handle_chat_message,
            ToClientCommand.TIME_OF_DAY: self._handle_time_of_day,
            ToClientCommand.UPDATE_PLAYER_LIST: self._handle_update_player_list,
            ToClientCommand.BLOCKDATA: self._handle_blockdata,
            ToClientCommand.PING: self._handle_ping,
        }
        self.formspec_handlers: dict[str, list[Callable[[str], None]]] = {}
        self.chat_message_handlers: list[Callable[[str], bool]] = []

    def process_command(self, command_id: int, data: bytes):
        """
        Processes a command by dispatching it to the appropriate handler.

        :param command_id: The ID of the command.
        :param data: The command data payload.
        """
        self.client.state.last_processed_command_id = command_id
        handler = self.handlers.get(command_id)
        if handler:
            logger.debug(f"Processing command 0x{command_id:02x}")
            handler(data)
        else:
            logger.debug(f"No handler for command 0x{command_id:02x}")

    def register_formspec_handler(self, formname: str, handler: Callable[[str], None]):
        """
        Registers a handler for a specific formspec name.

        :param formname: The name of the formspec (e.g., "miney:code_form").
        :param handler: A callable that takes the formspec content (str) as an argument.
        """
        handlers = self.formspec_handlers.setdefault(formname, [])
        handlers.append(handler)
        logger.debug(f"Registered formspec handler for '{formname}' (total={len(handlers)}).")

    def register_chat_message_handler(self, handler: Callable[[str], bool]):
        """
        Registers a handler for chat messages.

        Handlers are called in order of registration. If a handler returns True,
        processing stops for that message.

        :param handler: A callable that takes the message (str) and returns
                        True if handled, False otherwise.
        """
        self.chat_message_handlers.append(handler)
        logger.debug("Registered new chat message handler.")

    def _handle_hello(self, data: bytes):
        if self.client.state.authenticated:
            logger.debug("Already authenticated, ignoring duplicate HELLO.")
            return

        logger.debug("Received HELLO from server, starting authentication.")
        self.client.state.state = ClientState.AUTHENTICATING
        auth_methods = data[4]

        if self.client.register_mode:
            if auth_methods & 0x04:  # FIRST_SRP supported
                logger.info("Registering new user with FIRST_SRP.")
                self.client.send_first_srp()
            else:
                logger.warning("Server does not support FIRST_SRP registration. Falling back.")
                self.client.start_srp_auth()
        else:
            self.client.start_srp_auth()

    def _handle_auth_accept(self, data: bytes):
        logger.debug("Authentication successful.")
        self.client.state.authenticated = True
        self.client.state.state = ClientState.AUTHENTICATED
        # Player position is sent in this packet
        if len(data) >= 12:
            self.client.state._player_position["x"] = struct.unpack(">i", data[0:4])[0] / 100.0
            self.client.state._player_position["y"] = struct.unpack(">i", data[4:8])[0] / 100.0
            self.client.state._player_position["z"] = struct.unpack(">i", data[8:12])[0] / 100.0
        self.client.send_init2()

    def _handle_access_denied(self, data: bytes):
        reason_code = data[0]
        reason_message = self.client.get_access_denied_reason(reason_code)
        logger.error(f"Access denied: {reason_message} (code: {reason_code})")

        if reason_code == 10 and len(data) >= 3:  # Custom string
            str_len = struct.unpack(">H", data[1:3])[0]
            custom_reason = data[3:3 + str_len].decode('utf-8', 'replace')
            reason_message += f": {custom_reason}"
            logger.error(f"Custom reason: {custom_reason}")

        if self.client.register_mode and reason_code == 0:
            reason_message = "User already exists. Try logging in without registration."
            logger.error(reason_message)

        self.client.state.access_denied_reason = reason_message
        self.client.state.access_denied_code = reason_code
        self.client.state.state = ClientState.DISCONNECTED
        raise LuantiConnectionError(f"Access denied: {reason_message}", reason_code=reason_code)

    def _handle_srp_bytes_s_b(self, data: bytes):
        logger.debug("Received SRP bytes S and B from server.")
        pos = 0
        bytes_s_len = struct.unpack(">H", data[pos:pos + 2])[0]; pos += 2
        bytes_s = data[pos:pos + bytes_s_len]; pos += bytes_s_len
        bytes_B_len = struct.unpack(">H", data[pos:pos + 2])[0]; pos += 2
        bytes_B = data[pos:pos + bytes_B_len]

        try:
            M = self.client.state.srp_user.process_challenge(bytes_s, bytes_B)
            cmd = self.client.protocol.create_srp_bytes_m_command(M)
            self.client.send_packet(cmd)
            logger.debug(f"Sent SRP_BYTES_M proof.")
        except Exception as e:
            logger.error(f"Error during SRP challenge processing: {e}")

    def _handle_nodedef(self, data: bytes):
        if self.client.state.state < ClientState.JOINED:
            logger.debug("Node definitions received, client is now fully joined.")
            self.client.state.state = ClientState.JOINED

        data_len = struct.unpack(">I", data[0:4])[0]
        compressed_data = data[4:4 + data_len]
        self.client.state._node_definitions_raw = compressed_data
        logger.debug(f"Received node definitions data ({len(compressed_data)} bytes).")

        try:
            decompressed_data = zlib.decompress(compressed_data)
            self.client._parse_node_definitions(decompressed_data)
            if not self.client.state._has_node_definitions:
                self.client.state._has_node_definitions = True
                self.client.send_gotblocks()
        except zlib.error as e:
            logger.error(f"Failed to decompress node definitions: {e}")

    def _handle_show_formspec(self, data: bytes):
        pos = 0
        formspec_len = struct.unpack(">I", data[pos:pos + 4])[0]; pos += 4
        formspec = data[pos:pos + formspec_len].decode('utf-8', 'replace'); pos += formspec_len
        formname_len = struct.unpack(">H", data[pos:pos + 2])[0]; pos += 2
        formname = data[pos:pos + formname_len].decode('utf-8', 'replace')

        logger.debug(f"Received formspec '{formname}'")

        handlers = self.formspec_handlers.get(formname)
        if handlers:
            for h in list(handlers):
                try:
                    h(formspec)
                except Exception as e:
                    logger.error(f"Error in formspec handler for '{formname}': {e}", exc_info=True)
            return

        if formname == "__builtin:death":
            self._handle_death_screen()

    def _handle_death_screen(self):
        """Handles the death screen formspec."""
        if self.client.state.auto_respawn:
            logger.info("Auto-respawning after death.")
            fields = {"btn_respawn": "true"}
            self.client.send_formspec_response("__builtin:death", fields)
        else:
            logger.info("Received death screen, auto-respawn is disabled.")

    def _handle_chat_message(self, data: bytes):
        stream = io.BytesIO(data)
        stream.read(2)  # Skip version and type
        sender_len = struct.unpack(">H", stream.read(2))[0]
        sender = stream.read(sender_len * 2).decode('utf-16be', 'replace')
        message_len = struct.unpack(">H", stream.read(2))[0]
        message = stream.read(message_len * 2).decode('utf-16be', 'replace')
        logger.debug(f"Received a chat over client protocol from {sender}: {message}")

        for handler in self.chat_message_handlers:
            if handler(message):
                return

    def _handle_time_of_day(self, data: bytes):
        self.client.state._time_of_day = struct.unpack(">H", data[0:2])[0] / 24000.0
        self.client.state._time_speed = struct.unpack(">f", data[2:6])[0]
        logger.debug(f"Time updated: {self.client.state._time_of_day * 24.0:.2f}h")

    def _handle_update_player_list(self, data: bytes):
        list_type = data[0]
        count = struct.unpack(">H", data[1:3])[0]
        pos = 3
        players = []
        for _ in range(count):
            name_len = struct.unpack(">H", data[pos:pos + 2])[0]; pos += 2
            players.append(data[pos:pos + name_len].decode('utf-8', 'replace')); pos += name_len

        if list_type == 0:  # SET
            self.client.state._connected_players = players
        elif list_type == 1:  # ADD
            self.client.state._connected_players.extend(
                p for p in players if p not in self.client.state._connected_players)
        elif list_type == 2:  # REMOVE
            self.client.state._connected_players = [
                p for p in self.client.state._connected_players if p not in players]
        logger.debug(f"Player list updated: {self.client.state._connected_players}")

    def _handle_blockdata(self, data: bytes):
        pos_x, pos_y, pos_z = struct.unpack(">hhh", data[0:6])
        self.client.state._blocks[(pos_x, pos_y, pos_z)] = data[6:]
        logger.debug(f"Received block data for ({pos_x},{pos_y},{pos_z})")

    def _handle_ping(self, data: bytes):
        logger.debug("Received PING from server.")
