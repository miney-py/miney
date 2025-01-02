"""
Handles low-level network communication for the Luanti client.
"""
import socket
import struct
import threading
import time
import logging
from typing import Callable

from .protocol import Protocol, OriginalPacketPayload, SplitPacketPayload, ControlPacketData
from .state import ClientStateHolder

logger = logging.getLogger(__name__)


class Connection:
    """
    Manages the UDP socket, the send/receive loop, and packet transmission.
    """

    def __init__(self, host: str, port: int, protocol: Protocol, state: ClientStateHolder,
                 command_processor: Callable):
        """
        Initializes the Connection handler.

        :param host: The server host.
        :param port: The server port.
        :param protocol: The protocol instance for packet creation/parsing.
        :param state: The shared client state holder.
        :param command_processor: A callable to process incoming commands.
        """
        self.host = host
        self.port = port
        self.protocol = protocol
        self.state = state
        self.command_processor = command_processor

        self.sock: socket.socket | None = None
        self.receive_thread: threading.Thread | None = None
        self.running = False

        # For split packets
        self.split_packets = {}
        self.split_seqnum = 0

    def establish(self) -> bool:
        """
        Establishes the initial socket connection and handshake with the server.

        :return: True if the handshake was successful, False otherwise.
        """
        logger.info(f"Establishing connection to {self.host}:{self.port}")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(5.0)

        try:
            self.sock.bind(('0.0.0.0', 0))
            logger.debug(f"Bound to local port {self.sock.getsockname()[1]}")

            # Initial handshake packet
            packet = struct.pack(">I", self.protocol.protocol_id) + struct.pack(">HB", 0, 0)
            self.sock.sendto(packet, (self.host, self.port))
            self.state.packets_sent += 1

            data, addr = self.sock.recvfrom(1024)
            self.state.packets_received += 1
            logger.debug(f"Received handshake response: {data.hex()}")

            if len(data) < 14:
                logger.error("Invalid response during handshake - too short")
                return False

            if struct.unpack(">I", data[0:4])[0] == self.protocol.protocol_id:
                self.state.peer_id = struct.unpack(">H", data[12:14])[0]
            else:
                self.state.peer_id = struct.unpack(">H", data[4:6])[0]
            logger.debug(f"Assigned peer_id: {self.state.peer_id}")

            self.state.connected = True
            self.start_receiver()
            return True
        except socket.timeout:
            logger.error("Connection timed out during handshake")
            return False
        except Exception as e:
            logger.error(f"Error establishing connection: {e}")
            return False

    def disconnect(self):
        """Disconnects from the server and cleans up resources."""
        self.stop_receiver()

        if self.state.connected and self.state.peer_id is not None and self.sock and not self.state.access_denied_reason:
            logger.info("Disconnecting from server")
            try:
                packet = self.protocol.create_disconnect_packet(self.state.peer_id)
                self.sock.sendto(packet, (self.host, self.port))
                self.state.packets_sent += 1
                logger.debug("Sent disconnect packet to server")
                time.sleep(0.2)
            except Exception as e:
                logger.error(f"Error sending disconnect packet: {e}")

        if self.sock:
            self.sock.close()
            self.sock = None
            logger.debug("Socket closed")

        self.state.connected = False
        self.state.authenticated = False
        logger.debug(
            f"Connection stats: {self.state.packets_sent} sent, {self.state.packets_received} received")

    def start_receiver(self):
        """Starts the background thread for receiving packets and sending keep-alives."""
        if not self.receive_thread or not self.receive_thread.is_alive():
            self.running = True
            self.receive_thread = threading.Thread(target=self._receive_and_keep_alive_loop)
            self.receive_thread.daemon = True
            self.receive_thread.start()
            logger.debug("Receiver thread started.")

    def stop_receiver(self):
        """Stops the background receiver thread."""
        self.running = False
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=1.0)
            logger.debug("Receiver thread stopped.")

    def _receive_and_keep_alive_loop(self):
        last_keep_alive_time = time.time()
        keep_alive_interval = 2.0

        while self.running:
            current_time = time.time()
            if current_time - last_keep_alive_time >= keep_alive_interval and self.state.connected and self.state.peer_id is not None:
                try:
                    packet = self.protocol.create_keep_alive_packet(self.state.peer_id)
                    self.sock.sendto(packet, (self.host, self.port))
                    self.state.packets_sent += 1
                    logger.debug("Sent keep-alive control packet")
                    self._cleanup_split_packets()
                    last_keep_alive_time = current_time
                except Exception as e:
                    if self.running:
                        logger.error(f"Error in keep-alive: {e}")

            try:
                self.sock.settimeout(1.0)
                data, addr = self.sock.recvfrom(4096)
                self.state.packets_received += 1
                logger.debug(f"Received packet from {addr} with length {len(data)}")

                parsed_packet = self.protocol.parse(data)
                if not parsed_packet:
                    logger.debug(f"Could not parse packet. Data: {data.hex()}")
                    continue

                if parsed_packet.type == 'reliable':
                    p = parsed_packet.content
                    self.send_ack(p.channel, p.seqnum)
                    if isinstance(p.payload, OriginalPacketPayload):
                        self.command_processor(p.payload.command_id, p.payload.data)
                    elif isinstance(p.payload, SplitPacketPayload):
                        self._handle_split_packet(p.payload)
                    elif isinstance(p.payload, ControlPacketData) and p.payload.ctrl_type == 1 and len(
                            p.payload.payload) >= 2:
                        new_peer_id = struct.unpack(">H", p.payload.payload[0:2])[0]
                        logger.debug(
                            f"Updating peer_id from {self.state.peer_id} to {new_peer_id}")
                        self.state.peer_id = new_peer_id

                elif parsed_packet.type == 'control':
                    p = parsed_packet.content
                    if p.ctrl_type == 1 and len(p.payload) >= 2:
                        new_peer_id = struct.unpack(">H", p.payload[0:2])[0]
                        logger.debug(
                            f"Updating peer_id from {self.state.peer_id} to {new_peer_id}")
                        self.state.peer_id = new_peer_id

                elif parsed_packet.type == 'direct_command':
                    p = parsed_packet.content
                    self.command_processor(p.command_id, p.data)

            except socket.timeout:
                pass
            except Exception as e:
                if self.running:
                    logger.error(f"Error in receive loop: {e}", exc_info=True)

    def _cleanup_split_packets(self):
        current_time = time.time()
        expired = [k for k, v in self.split_packets.items() if current_time - v['received_time'] > 30]
        for seqnum in expired:
            logger.debug(f"Removing expired split packet {seqnum}")
            del self.split_packets[seqnum]

    def send_ack(self, channel: int, seqnum: int):
        try:
            packet = self.protocol.create_ack_packet(self.state.peer_id, channel, seqnum)
            self.sock.sendto(packet, (self.host, self.port))
            logger.debug(f"Sent ACK for seqnum {seqnum}")
        except Exception as e:
            logger.error(f"Error sending ACK for seqnum {seqnum}: {e}")

    def _handle_split_packet(self, payload: SplitPacketPayload):
        if payload.split_seqnum not in self.split_packets:
            self.split_packets[payload.split_seqnum] = {
                'chunks': {},
                'total_chunks': payload.chunk_count,
                'received_time': time.time()
            }
        self.split_packets[payload.split_seqnum]['chunks'][payload.chunk_num] = payload.chunk_data

        if len(self.split_packets[payload.split_seqnum]['chunks']) == payload.chunk_count:
            logger.debug(f"All chunks for split packet {payload.split_seqnum} received")
            data = b''.join(
                self.split_packets[payload.split_seqnum]['chunks'][i] for i in
                range(payload.chunk_count))
            del self.split_packets[payload.split_seqnum]

            if len(data) >= 2:
                command_id = struct.unpack(">H", data[0:2])[0]
                self.command_processor(command_id, data[2:])

    def _get_next_split_seqnum(self) -> int:
        seqnum = self.split_seqnum
        self.split_seqnum = (self.split_seqnum + 1) % 65536
        return seqnum

    def send_split_packet(self, data: bytes) -> bool:
        HEADER_SIZE = 17
        MAX_CHUNK_SIZE = 512 - HEADER_SIZE
        total_chunks = (len(data) + MAX_CHUNK_SIZE - 1) // MAX_CHUNK_SIZE
        if total_chunks > 65535:
            logger.error(f"Data too large to split: {len(data)} bytes")
            return False

        split_seqnum = self._get_next_split_seqnum()
        logger.info(f"Splitting packet of {len(data)} bytes into {total_chunks} chunks")

        for i in range(total_chunks):
            offset = i * MAX_CHUNK_SIZE
            chunk_data = data[offset:offset + min(MAX_CHUNK_SIZE, len(data) - offset)]
            packet = self.protocol.create_reliable_split_packet(
                peer_id=self.state.peer_id, sequence_number=self.state.sequence_number,
                split_seqnum=split_seqnum, total_chunks=total_chunks, chunk_num=i,
                chunk_data=chunk_data)
            self.state.sequence_number = (self.state.sequence_number + 1) % 65536
            try:
                self.sock.sendto(packet, (self.host, self.port))
                self.state.packets_sent += 1
                time.sleep(0.01)
            except Exception as e:
                logger.error(f"Error sending split chunk {i + 1}/{total_chunks}: {e}")
                return False
        return True

    def send_packet(self, data: bytes) -> bool:
        if not self.state.connected or self.state.peer_id is None:
            logger.warning("Cannot send packet: not connected or peer_id not set")
            return False

        HEADER_SIZE = 11
        MAX_SINGLE_PACKET_SIZE = 512 - HEADER_SIZE
        if len(data) > MAX_SINGLE_PACKET_SIZE:
            return self.send_split_packet(data)

        packet = self.protocol.create_reliable_original_packet(
            peer_id=self.state.peer_id,
            sequence_number=self.state.sequence_number,
            data=data)
        self.state.sequence_number = (self.state.sequence_number + 1) % 65536
        try:
            self.sock.sendto(packet, (self.host, self.port))
            self.state.packets_sent += 1
            return True
        except Exception as e:
            logger.error(f"Error sending packet: {e}")
            return False
