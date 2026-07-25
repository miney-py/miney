"""
Handles low-level network communication for the Luanti client.
"""
import socket
import struct
import threading
import time
import logging
from dataclasses import dataclass
from typing import Callable

from .protocol import Protocol, OriginalPacketPayload, SplitPacketPayload, ControlPacketData
from .state import ClientStateHolder

logger = logging.getLogger(__name__)

# Reliable delivery. These are Luanti's own numbers, taken from its connection layer
# so that both ends agree about what "reliable" means.
#
# SEND_WINDOW is how many packets may be unacknowledged at once. It is the engine's
# START_RELIABLE_WINDOW_SIZE (src/network/mtp/internal.h). It is what paces the sender:
# a full window blocks until an ACK frees a slot, which on a fast link is no wait at
# all and on a slow one is exactly as much waiting as the link needs.
SEND_WINDOW = 64

# How long to wait for an ACK before sending the packet again. The engine's own default
# (`resend_timeout = 0.5`, internal.h), and its floor for an adaptive value is 0.1.
RESEND_TIMEOUT = 0.5

# Give up after this many attempts. The engine drops the peer at this point; Miney lets
# the layer above notice, because "the answer never came" is a better error for a user
# than a connection that vanished.
MAX_SEND_TRIES = 5

# How long a full window may block before the send is abandoned.
SEND_STALL_TIMEOUT = 30.0

# How often the receive loop wakes up. It only needs to be quick while there is
# something to retransmit; the rest of the time it idles on the socket.
POLL_WHILE_SENDING = 0.05
POLL_WHILE_IDLE = 1.0


@dataclass
class _Unacked:
    """A reliable packet that has been sent and not yet acknowledged."""
    packet: bytes
    sent_at: float
    tries: int


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
        self.seqnum_lock = threading.Lock()
        self.split_seqnum_lock = threading.Lock()

        # Reliable packets that are on their way out and not yet acknowledged, by
        # sequence number. The receiver thread removes entries as ACKs arrive and
        # wakes anyone waiting for a free window slot.
        self._unacked: dict[int, _Unacked] = {}
        self._unacked_cond = threading.Condition()

    def establish(self) -> bool:
        """
        Establishes the initial socket connection and handshake with the server.

        :return: True if the handshake was successful, False otherwise.
        """
        logger.debug(f"Establishing connection to {self.host}:{self.port}")
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
        # Before the receiver stops, because it is the thread that collects ACKs. A
        # last message that is still in flight gets a moment to land.
        self._wait_for_acks(timeout=0.5)
        self.stop_receiver()

        if self.state.connected and self.state.peer_id is not None and self.sock and not self.state.access_denied_reason:
            logger.debug("Disconnecting from server")
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
        """
        Stops the background receiver thread.

        The join is allowed to fail. A script that never used ``with`` leaves the
        disconnect to ``Luanti.__del__``, which the interpreter calls while it is
        already shutting down - and joining a thread at that point raises
        ``PythonFinalizationError`` (a ``RuntimeError``, since Python 3.13). That
        exception used to escape through :meth:`disconnect` before it got to send the
        disconnect packet, so the server kept the session alive until it timed out and
        the next run of the same script was refused with *"Another client is already
        connected with this name."* The thread is a daemon and the process is ending
        anyway, so not waiting for it costs nothing; getting the packet out is what
        matters.
        """
        self.running = False
        with self._unacked_cond:  # let go of anyone waiting for a window slot
            self._unacked_cond.notify_all()
        if self.receive_thread and self.receive_thread.is_alive():
            try:
                self.receive_thread.join(timeout=1.0)
                logger.debug("Receiver thread stopped.")
            except RuntimeError as e:
                logger.debug(f"Could not join the receiver thread, continuing anyway: {e}")

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

            self._resend_expired()

            try:
                # Only wake up often while there is something waiting to be
                # acknowledged; an idle connection goes back to sitting on the socket.
                self.sock.settimeout(
                    POLL_WHILE_SENDING if self._unacked else POLL_WHILE_IDLE)
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

                elif parsed_packet.type == 'ack':
                    self._handle_ack(parsed_packet.content.seqnum)

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

    def _send_reliable(self, packet: bytes, seqnum: int) -> bool:
        """
        Send a reliable packet and keep it until the server acknowledges it.

        This is the whole of Miney's flow control. Luanti acknowledges every reliable
        packet it accepts, and deliberately does *not* acknowledge one that arrives too
        far ahead of what it expects - its own comment there reads *"if this was a valid
        packet it's gonna be retransmitted"*. Miney never retransmitted, so a packet lost
        to a full socket buffer or to the network was lost for good: the split message it
        belonged to never completed and the call above waited out its timeout for an
        answer that could not come. The old code avoided that by sending slowly enough
        that it rarely happened - 495 bytes every 10 ms, about 45 KB/s.

        With the packet kept and resent, speed stops being dangerous. What limits the
        rate now is :data:`SEND_WINDOW` packets in flight: a full window waits for an
        ACK, so a fast link runs at its own speed and a slow one is throttled to a window
        per round trip, which is what a sender is supposed to do.

        :param packet: The fully built packet, kept verbatim so a resend is identical.
        :param seqnum: Its sequence number, which is how the ACK will name it.
        :return: True if it went out, False if the window never cleared or the socket
            refused it.
        """
        with self._unacked_cond:
            deadline = time.monotonic() + SEND_STALL_TIMEOUT
            while len(self._unacked) >= SEND_WINDOW:
                if not self.running:
                    logger.debug("Receiver stopped while waiting for a window slot.")
                    return False
                self._unacked_cond.wait(timeout=0.1)
                if time.monotonic() > deadline:
                    logger.error(
                        f"No acknowledgement for {SEND_WINDOW} packets in "
                        f"{SEND_STALL_TIMEOUT:.0f}s - giving up on this send.")
                    return False
            self._unacked[seqnum] = _Unacked(packet, time.monotonic(), 1)

        try:
            self.sock.sendto(packet, (self.host, self.port))
            self.state.packets_sent += 1
            return True
        except Exception as e:
            logger.error(f"Error sending reliable packet {seqnum}: {e}")
            with self._unacked_cond:
                self._unacked.pop(seqnum, None)
                self._unacked_cond.notify_all()
            return False

    def _handle_ack(self, seqnum: int):
        """
        Retire an acknowledged packet and free its window slot.

        :param seqnum: The sequence number the server acknowledged.
        """
        with self._unacked_cond:
            if self._unacked.pop(seqnum, None) is not None:
                self._unacked_cond.notify_all()

    def _resend_expired(self):
        """
        Send again anything that has gone unacknowledged for too long.

        Called from the receive loop, which is the only thread that learns about ACKs.
        The packets are collected under the lock and sent outside it, so a slow socket
        cannot hold up the ACKs that would empty the queue.
        """
        if not self._unacked:
            return

        now = time.monotonic()
        due: list[bytes] = []
        with self._unacked_cond:
            for seqnum, pending in list(self._unacked.items()):
                if now - pending.sent_at < RESEND_TIMEOUT:
                    continue
                if pending.tries >= MAX_SEND_TRIES:
                    logger.error(
                        f"Packet {seqnum} was not acknowledged after "
                        f"{MAX_SEND_TRIES} attempts - dropping it.")
                    del self._unacked[seqnum]
                    continue
                pending.tries += 1
                pending.sent_at = now
                due.append(pending.packet)
                logger.debug(f"Resending packet {seqnum}, attempt {pending.tries}")
            self._unacked_cond.notify_all()

        for packet in due:
            try:
                self.sock.sendto(packet, (self.host, self.port))
                self.state.packets_sent += 1
            except Exception as e:
                logger.error(f"Error resending a packet: {e}")

    def _wait_for_acks(self, timeout: float):
        """
        Wait until everything sent has been acknowledged, or until time runs out.

        Used on the way out, so that a last message is not still sitting in the queue
        when the socket closes.

        :param timeout: How long to wait, in seconds.
        """
        deadline = time.monotonic() + timeout
        with self._unacked_cond:
            while self._unacked and self.running:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    logger.debug(
                        f"{len(self._unacked)} packets still unacknowledged at "
                        f"disconnect.")
                    return
                self._unacked_cond.wait(timeout=remaining)

    def _get_next_split_seqnum(self) -> int:
        with self.split_seqnum_lock:
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
        logger.debug(f"Splitting packet of {len(data)} bytes into {total_chunks} chunks")

        for i in range(total_chunks):
            offset = i * MAX_CHUNK_SIZE
            chunk_data = data[offset:offset + min(MAX_CHUNK_SIZE, len(data) - offset)]
            with self.seqnum_lock:
                seqnum = self.state.sequence_number
                packet = self.protocol.create_reliable_split_packet(
                    peer_id=self.state.peer_id, sequence_number=seqnum,
                    split_seqnum=split_seqnum, total_chunks=total_chunks, chunk_num=i,
                    chunk_data=chunk_data)
                self.state.sequence_number = (self.state.sequence_number + 1) % 65536
            if not self._send_reliable(packet, seqnum):
                logger.error(f"Error sending split chunk {i + 1}/{total_chunks}")
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

        with self.seqnum_lock:
            seqnum = self.state.sequence_number
            packet = self.protocol.create_reliable_original_packet(
                peer_id=self.state.peer_id,
                sequence_number=seqnum,
                data=data)
            self.state.sequence_number = (self.state.sequence_number + 1) % 65536
        return self._send_reliable(packet, seqnum)
