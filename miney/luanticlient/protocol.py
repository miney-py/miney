import struct
import logging
from collections import namedtuple

from .constants import ToServerCommand

logger = logging.getLogger(__name__)

# Packet data structures
PacketData = namedtuple('PacketData', ['type', 'content'])
ReliablePacketData = namedtuple('ReliablePacketData', ['peer_id', 'channel', 'seqnum', 'payload'])
OriginalPacketPayload = namedtuple('OriginalPacketPayload', ['command_id', 'data'])
SplitPacketPayload = namedtuple('SplitPacketPayload',
                                ['split_seqnum', 'chunk_count', 'chunk_num', 'chunk_data'])
ControlPacketData = namedtuple('ControlPacketData', ['peer_id', 'channel', 'ctrl_type', 'payload'])
AckPacketData = namedtuple('AckPacketData', ['peer_id', 'channel', 'seqnum'])
DirectCommandData = namedtuple('DirectCommandData', ['command_id', 'data'])


class Protocol:
    """
    Handles serialization and deserialization of Luanti network packets.
    """

    def __init__(self, protocol_id: int, serialization_version: int, protocol_version: int, version_string: str):
        self.protocol_id = protocol_id
        self.serialization_version = serialization_version
        self.protocol_version = protocol_version
        self.version_string = version_string

    def create_init_payload(self, username: str, password: str) -> bytes:
        """
        Creates the payload for an INIT command.

        :param username: The playername.
        :param password: The password.
        :return: The serialized payload.
        """
        serialization_ver = struct.pack(">B", self.serialization_version)
        compression = struct.pack(">H", 0)
        min_proto = struct.pack(">H", self.protocol_version)
        max_proto = struct.pack(">H", self.protocol_version)
        username_bytes = username.encode('utf-8')
        username_len = struct.pack(">H", len(username_bytes))
        password_bytes = password.encode('utf-8')
        password_len = struct.pack(">H", len(password_bytes))
        return serialization_ver + compression + min_proto + max_proto + username_len + username_bytes + password_len + password_bytes

    def create_init_command(self, username: str, password: str) -> bytes:
        """
        Creates the data for an INIT command.

        :param username: The playername.
        :param password: The password.
        :return: The serialized command data.
        """
        command = struct.pack(">H", ToServerCommand.INIT)
        payload = self.create_init_payload(username, password)
        return command + payload

    def create_init2_command(self) -> bytes:
        """
        Creates the data for an INIT2 command.

        :return: The serialized command data.
        """
        return struct.pack(">H", ToServerCommand.INIT2)

    def create_client_ready_command(self) -> bytes:
        """
        Creates the data for a CLIENT_READY command.

        :return: The serialized command data.
        """
        command = struct.pack(">H", ToServerCommand.CLIENT_READY)
        version = struct.pack(">BBBB", 5, 7, 0, 0)
        version_str = self.version_string.encode('utf-8')
        version_len = struct.pack(">H", len(version_str))
        return command + version + version_len + version_str

    def create_gotblocks_command(self, x: int, y: int, z: int) -> bytes:
        """
        Creates the data for a GOTBLOCKS command.

        :param x: The x-coordinate of the block.
        :param y: The y-coordinate of the block.
        :param z: The z-coordinate of the block.
        :return: The serialized command data.
        """
        command = struct.pack(">H", ToServerCommand.GOTBLOCKS)
        payload = struct.pack(">hhh", x, y, z)
        return command + payload

    def create_chat_message_command(self, message: str) -> bytes:
        """
        Creates the data for a CHAT_MESSAGE command.

        :param message: The chat message.
        :return: The serialized command data.
        """
        command = struct.pack(">H", ToServerCommand.CHAT_MESSAGE)
        message_bytes = message.encode('utf-16be')
        length = struct.pack(">H", len(message_bytes) // 2)
        return command + length + message_bytes

    def create_first_srp_command(self, salt: bytes, verifier: bytes, is_empty: bool) -> bytes:
        """
        Creates the data for a FIRST_SRP command.

        :param salt: The salt for SRP.
        :param verifier: The verifier for SRP.
        :param is_empty: True if the password is empty.
        :return: The serialized command data.
        """
        command = struct.pack(">H", ToServerCommand.FIRST_SRP)
        salt_len = struct.pack(">H", len(salt))
        v_len = struct.pack(">H", len(verifier))
        is_empty_byte = struct.pack(">B", 1 if is_empty else 0)
        return command + salt_len + salt + v_len + verifier + is_empty_byte

    def create_formspec_response_command(self, formname: str, fields: dict) -> bytes:
        """
        Creates the data for an INVENTORY_FIELDS (formspec response) command.

        :param formname: The name of the form.
        :param fields: A dictionary of form fields and values.
        :return: The serialized command data.
        """
        command = struct.pack(">H", ToServerCommand.INVENTORY_FIELDS)
        formname_bytes = formname.encode('utf-8')
        formname_len = struct.pack(">H", len(formname_bytes))
        field_count = struct.pack(">H", len(fields))
        packet = command + formname_len + formname_bytes + field_count

        for key, value in fields.items():
            key_bytes = key.encode('utf-8')
            key_len = struct.pack(">H", len(key_bytes))
            value_bytes = str(value).encode('utf-8')
            value_len = struct.pack(">I", len(value_bytes))
            packet += key_len + key_bytes + value_len + value_bytes
        return packet

    def create_srp_bytes_a_command(self, bytes_A: bytes) -> bytes:
        """
        Creates the data for an SRP_BYTES_A command.

        :param bytes_A: The client's public value A.
        :return: The serialized command data.
        """
        based_on = 1
        command = struct.pack(">H", ToServerCommand.SRP_BYTES_A)
        command += struct.pack(">H", len(bytes_A))
        command += bytes_A
        command += struct.pack(">B", based_on)
        return command

    def create_srp_bytes_m_command(self, bytes_M: bytes) -> bytes:
        """
        Creates the data for an SRP_BYTES_M command.

        :param bytes_M: The client's proof M.
        :return: The serialized command data.
        """
        command = struct.pack(">H", ToServerCommand.SRP_BYTES_M)
        command += struct.pack(">H", len(bytes_M))
        command += bytes_M
        return command

    def create_reliable_original_packet(self, peer_id: int, sequence_number: int, data: bytes) -> bytes:
        """
        Creates a reliable original packet.

        :param peer_id: The peer ID of the client.
        :param sequence_number: The sequence number for the reliable packet.
        :param data: The payload (command + data).
        :return: The full serialized packet.
        """
        basic_header = struct.pack(">I", self.protocol_id)
        basic_header += struct.pack(">H", peer_id)
        basic_header += struct.pack(">B", 0)  # channel
        reliable_header = struct.pack(">B", 3)  # PACKET_TYPE_RELIABLE
        reliable_header += struct.pack(">H", sequence_number)
        original_header = struct.pack(">B", 1)  # PACKET_TYPE_ORIGINAL
        return basic_header + reliable_header + original_header + data

    def create_reliable_split_packet(self, peer_id: int, sequence_number: int, split_seqnum: int,
                                     total_chunks: int, chunk_num: int, chunk_data: bytes) -> bytes:
        """
        Creates a reliable split packet chunk.

        :param peer_id: The peer ID of the client.
        :param sequence_number: The sequence number for the reliable packet.
        :param split_seqnum: The sequence number for the split packet series.
        :param total_chunks: The total number of chunks.
        :param chunk_num: The current chunk number.
        :param chunk_data: The data for this chunk.
        :return: The full serialized packet chunk.
        """
        split_header = struct.pack(">B", 2)  # PACKET_TYPE_SPLIT
        split_header += struct.pack(">H", split_seqnum)
        split_header += struct.pack(">H", total_chunks)
        split_header += struct.pack(">H", chunk_num)

        basic_header = struct.pack(">I", self.protocol_id)
        basic_header += struct.pack(">H", peer_id)
        basic_header += struct.pack(">B", 0)  # channel

        reliable_header = struct.pack(">B", 3)  # PACKET_TYPE_RELIABLE
        reliable_header += struct.pack(">H", sequence_number)

        return basic_header + reliable_header + split_header + chunk_data

    def create_ack_packet(self, peer_id: int, channel: int, seqnum: int) -> bytes:
        """
        Creates an ACK packet.

        :param peer_id: The peer ID of the client.
        :param channel: The channel of the packet to acknowledge.
        :param seqnum: The sequence number of the packet to acknowledge.
        :return: The full serialized ACK packet.
        """
        packet = struct.pack(">I", self.protocol_id)
        packet += struct.pack(">H", peer_id)
        packet += struct.pack(">B", channel)
        packet += struct.pack(">B", 0)  # Control packet
        packet += struct.pack(">B", 0)  # ACK type
        packet += struct.pack(">H", seqnum)
        return packet

    def create_disconnect_packet(self, peer_id: int) -> bytes:
        """
        Creates a disconnect packet.

        :param peer_id: The peer ID of the client.
        :return: The full serialized disconnect packet.
        """
        packet = struct.pack(">I", self.protocol_id) + struct.pack(">HB", peer_id, 0)
        packet += struct.pack(">B", 0)  # Control-Paket
        packet += struct.pack(">B", 3)  # Disconnect-Typ
        return packet

    def create_keep_alive_packet(self, peer_id: int) -> bytes:
        """
        Creates a keep-alive packet.

        :param peer_id: The peer ID of the client.
        :return: The full serialized keep-alive packet.
        """
        packet = struct.pack(">I", self.protocol_id) + struct.pack(">HB", peer_id, 0)
        packet += struct.pack(">B", 0)  # Control packet
        packet += struct.pack(">B", 2)  # Keep-alive type
        return packet

    def parse(self, data: bytes) -> PacketData | None:
        """
        Parses raw packet data into a structured format.

        :param data: The raw bytes received from the network.
        :return: A PacketData named tuple or None if parsing fails.
        """
        if len(data) >= 4 and struct.unpack(">I", data[0:4])[0] == self.protocol_id:
            if len(data) < 7:
                return None  # Too short for a standard protocol packet

            peer_id = struct.unpack(">H", data[4:6])[0]
            channel = data[6]
            packet_type_byte = data[7]

            if packet_type_byte == 3:  # RELIABLE
                if len(data) < 10: return None
                seqnum = struct.unpack(">H", data[8:10])[0]
                payload_type = data[10]

                if payload_type == 1:  # ORIGINAL
                    if len(data) < 13: return None
                    command_id = struct.unpack(">H", data[11:13])[0]
                    payload = OriginalPacketPayload(command_id, data[13:])
                    return PacketData('reliable', ReliablePacketData(peer_id, channel, seqnum, payload))
                elif payload_type == 2:  # SPLIT
                    if len(data) < 17: return None
                    split_seqnum = struct.unpack(">H", data[11:13])[0]
                    chunk_count = struct.unpack(">H", data[13:15])[0]
                    chunk_num = struct.unpack(">H", data[15:17])[0]
                    chunk_data = data[17:]
                    payload = SplitPacketPayload(split_seqnum, chunk_count, chunk_num, chunk_data)
                    return PacketData('reliable', ReliablePacketData(peer_id, channel, seqnum, payload))
                elif payload_type == 0:  # CONTROL (within a reliable packet)
                    if len(data) < 12: return None
                    # This is a control packet wrapped in a reliable one.
                    # We need to ACK the reliable wrapper, so we return a 'reliable' packet
                    # containing the control payload.
                    ctrl_type = data[11]
                    payload_data = data[12:]
                    payload = ControlPacketData(peer_id, channel, ctrl_type, payload_data)
                    return PacketData('reliable', ReliablePacketData(peer_id, channel, seqnum, payload))

            elif packet_type_byte == 0:  # CONTROL
                if len(data) < 9: return None
                ctrl_type = data[8]
                payload = data[9:]
                if ctrl_type == 0:  # ACK
                    if len(data) < 11: return None
                    seqnum = struct.unpack(">H", data[9:11])[0]
                    return PacketData('ack', AckPacketData(peer_id, channel, seqnum))
                else:
                    return PacketData('control', ControlPacketData(peer_id, channel, ctrl_type, payload))

        elif len(data) >= 2:
            # This is not a standard protocol packet, but it could be a direct command
            # or another type of packet sent without the protocol ID header (like in luanti_old.py).
            # The old implementation treated these as direct commands. We will replicate that.
            try:
                command_id = struct.unpack(">H", data[0:2])[0]
                return PacketData('direct_command', DirectCommandData(command_id, data[2:]))
            except struct.error:
                logger.debug(f"Could not parse non-protocol packet of length {len(data)}")
                return None

        return None
