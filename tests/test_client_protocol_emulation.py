from __future__ import annotations
import struct
import time
import zlib
import socket
from typing import Any, List, Tuple

import pytest

from miney.luanticlient.client import LuantiClient
from miney.luanticlient.protocol import Protocol
from miney.luanticlient.constants import ToServerCommand, ToClientCommand, ClientState
from miney.luanticlient.exceptions import LuantiConnectionError


class FakeSocket:
    """
    Minimal in-memory UDP socket emulation with a paired FakeServer, used via monkeypatch.
    """
    def __init__(self, server: "FakeServer"):
        self._server = server
        self._inbox: List[Tuple[bytes, Tuple[str, int]]] = []
        self._closed = False
        self._timeout = 5.0
        self._local_port = 0

    # --- socket API emulation ---
    def settimeout(self, value: float) -> None:
        self._timeout = value

    def bind(self, addr: Tuple[str, int]) -> None:
        self._local_port = addr[1]

    def getsockname(self) -> Tuple[str, int]:
        return ("127.0.0.1", self._local_port or 12345)

    def sendto(self, data: bytes, addr: Tuple[str, int]) -> int:
        # Forward client outbound data to the fake server, which may enqueue replies.
        self._server.on_client_send(self, data, addr)
        return len(data)

    def recvfrom(self, bufsize: int) -> Tuple[bytes, Tuple[str, int]]:
        # Wait up to timeout for a server message
        t_end = time.time() + self._timeout
        while time.time() < t_end:
            if self._inbox:
                return self._inbox.pop(0)
            time.sleep(0.005)
        raise socket.timeout()

    def close(self) -> None:
        self._closed = True

    # --- helpers for server to push data to client ---
    def _push_from_server(self, data: bytes) -> None:
        self._inbox.append((data, ("server", 30000)))


class FakeServer:
    """
    Stateless-enough server that reacts to client packets, built on the same Protocol.
    - Handles initial handshake (non-Protocol prelude)
    - Responds to INIT -> HELLO
    - Responds to SRP A -> SRP S,B
    - Responds to SRP M -> AUTH_ACCEPT and NODEDEF
    - Records outbound client commands for assertions
    """
    def __init__(self, deny: bool = False):
        self.protocol: Protocol | None = None
        self.peer_id = 0xBEEF
        self._client_sock: FakeSocket | None = None
        self.deny = deny
        self.recorded_client_cmds: list[int] = []
        self.recorded_inventory_fields: list[tuple[str, dict]] = []
        self.recorded_splits_outbound: int = 0

    def _ensure_protocol(self, protocol_id: int) -> None:
        if not self.protocol:
            # Version fields are not relevant for framing here; protocol_id must match.
            self.protocol = Protocol(protocol_id, serialization_version=28, protocol_version=39,
                                     version_string="miney_v1.0")

    def on_client_send(self, sock: FakeSocket, data: bytes, addr: Tuple[str, int]) -> None:
        self._client_sock = sock

        # Handshake prelude (raw, not Protocol.parse-able)
        if len(data) == 7 and struct.unpack(">I", data[0:4])[0]:
            proto_id = struct.unpack(">I", data[0:4])[0]
            self._ensure_protocol(proto_id)
            # Build minimal handshake response (>=14 bytes, peer_id at [12:14])
            resp = struct.pack(">I", proto_id) + b"\x00" * 8 + struct.pack(">H", self.peer_id)
            sock._push_from_server(resp)
            return

        # Try to parse as Protocol-framed packet
        parsed = self.protocol.parse(data) if self.protocol else None
        if not parsed:
            return

        if parsed.type == "reliable":
            p = parsed.content
            # Count outbound split packets (from client)
            # Payload type is not exposed here; we can infer by length of data vs header sizes.
            # Instead, parse() already decoded: if OriginalPacketPayload then process, else Split -> None here.
            payload = p.payload
            if hasattr(payload, "command_id"):
                self.recorded_client_cmds.append(payload.command_id)
                self._handle_client_original(payload.command_id, payload.data)
            else:
                # Client sent a split packet chunk
                self.recorded_splits_outbound += 1

        elif parsed.type == "control":
            # Ignore for tests
            pass

    def _send_reliable_original(self, command_id: int, payload: bytes) -> None:
        pkt = self.protocol.create_reliable_original_packet(self.peer_id, sequence_number=1,
                                                            data=struct.pack(">H", command_id) + payload)
        self._client_sock._push_from_server(pkt)

    def _handle_client_original(self, cmd_id: int, payload: bytes) -> None:
        if cmd_id == ToServerCommand.INIT:
            if self.deny:
                # Access denied, code=1 (arbitrary)
                self._send_reliable_original(ToClientCommand.ACCESS_DENIED, b"\x01")
                return
            # HELLO: set auth_methods so FIRST_SRP is supported (bit 0x04 at offset 4)
            hello_payload = b"\x00\x00\x00\x00" + b"\x04"
            self._send_reliable_original(ToClientCommand.HELLO, hello_payload)

        elif cmd_id == ToServerCommand.SRP_BYTES_A:
            # Reply with SRP_BYTES_S_B: [len_s][s][len_B][B]
            salt = b"\x11" * 16
            B = (1 << 2040) + 123456  # big number; non-zero mod N
            B_bytes = B.to_bytes((B.bit_length() + 7) // 8, "big")
            payload = struct.pack(">H", len(salt)) + salt + struct.pack(">H", len(B_bytes)) + B_bytes
            self._send_reliable_original(ToClientCommand.SRP_BYTES_S_B, payload)

        elif cmd_id == ToServerCommand.SRP_BYTES_M:
            # Authenticate and accept; include player position (x,y,z) as >i (centi-units)
            pos_payload = struct.pack(">iii", 100, 200, 300)
            self._send_reliable_original(ToClientCommand.AUTH_ACCEPT, pos_payload)
            # Send NODEDEF (compressed blob)
            compressed = zlib.compress(b"\x01\x02")
            payload = struct.pack(">I", len(compressed)) + compressed
            self._send_reliable_original(ToClientCommand.NODEDEF, payload)

        elif cmd_id == ToServerCommand.GOTBLOCKS:
            # No response needed
            pass

        elif cmd_id == ToServerCommand.INVENTORY_FIELDS:
            # Decode formspec response fields for assertions
            pos = 0
            formname_len = struct.unpack(">H", payload[pos:pos + 2])[0]; pos += 2
            formname = payload[pos:pos + formname_len].decode("utf-8", "replace"); pos += formname_len
            count = struct.unpack(">H", payload[pos:pos + 2])[0]; pos += 2
            fields: dict[str, Any] = {}
            for _ in range(count):
                klen = struct.unpack(">H", payload[pos:pos + 2])[0]; pos += 2
                key = payload[pos:pos + klen].decode("utf-8", "replace"); pos += klen
                vlen = struct.unpack(">I", payload[pos:pos + 4])[0]; pos += 4
                val = payload[pos:pos + vlen].decode("utf-8", "replace"); pos += vlen
                fields[key] = val
            self.recorded_inventory_fields.append((formname, fields))

    # --- utilities to push server events into client ---

    def push_show_formspec(self, formname: str, formspec: str) -> None:
        fs_bytes = formspec.encode("utf-8")
        name_bytes = formname.encode("utf-8")
        payload = struct.pack(">I", len(fs_bytes)) + fs_bytes + struct.pack(">H", len(name_bytes)) + name_bytes
        self._send_reliable_original(ToClientCommand.SHOW_FORMSPEC, payload)

    def push_chat(self, sender: str, message: str) -> None:
        s_bytes = sender.encode("utf-16be")
        m_bytes = message.encode("utf-16be")
        payload = b"\x00\x00"  # version/type skipped by client
        payload += struct.pack(">H", len(s_bytes) // 2) + s_bytes
        payload += struct.pack(">H", len(m_bytes) // 2) + m_bytes
        self._send_reliable_original(ToClientCommand.CHAT_MESSAGE, payload)

    def push_time_of_day(self, tod_0_24000: int, speed: float) -> None:
        payload = struct.pack(">Hf", tod_0_24000, speed)
        self._send_reliable_original(ToClientCommand.TIME_OF_DAY, payload)

    def push_update_player_list(self, list_type: int, players: list[str]) -> None:
        payload = bytes([list_type]) + struct.pack(">H", len(players))
        for p in players:
            b = p.encode("utf-8")
            payload += struct.pack(">H", len(b)) + b
        self._send_reliable_original(ToClientCommand.UPDATE_PLAYER_LIST, payload)

    def push_blockdata(self, x: int, y: int, z: int, data: bytes) -> None:
        payload = struct.pack(">hhh", x, y, z) + data
        self._send_reliable_original(ToClientCommand.BLOCKDATA, payload)

    def push_split_ping(self) -> None:
        # Build a reconstructed Original payload: [cmd_id=PING][no payload]
        original = struct.pack(">H", ToClientCommand.PING)
        # Split into 2 chunks
        split_seqnum = 7
        total_chunks = 2
        chunks = [original[:1], original[1:]]
        for i, chunk in enumerate(chunks):
            pkt = self.protocol.create_reliable_split_packet(
                peer_id=self.peer_id, sequence_number=10 + i,
                split_seqnum=split_seqnum, total_chunks=total_chunks,
                chunk_num=i, chunk_data=chunk)
            self._client_sock._push_from_server(pkt)


@pytest.fixture
def fake_server(monkeypatch):
    server = FakeServer()

    def socket_factory(*args, **kwargs):
        return FakeSocket(server)

    monkeypatch.setattr("miney.luanticlient.connection.socket.socket", socket_factory)
    return server


def _wait_for(predicate, timeout: float = 2.0) -> None:
    t_end = time.time() + timeout
    while time.time() < t_end:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Timeout waiting for condition")


def test_connect_success_and_events(fake_server: FakeServer, monkeypatch):
    client = LuantiClient(playername="Tester", password="pw")
    assert client.connect() is True
    assert client.state.state == ClientState.JOINED
    assert client.state.authenticated is True

    # formspec dispatch to registered handler
    calls: list[str] = []
    client.command_handler.register_formspec_handler("miney:code_form", lambda s: calls.append(s))
    fake_server.push_show_formspec("miney:code_form", "hello-json-or-legacy")
    _wait_for(lambda: calls == ["hello-json-or-legacy"])

    # death screen auto-respawn sends formspec response
    fake_server.push_show_formspec("__builtin:death", "dead")
    _wait_for(lambda: any(f[0] == "__builtin:death" for f in fake_server.recorded_inventory_fields))
    formname, fields = next(f for f in fake_server.recorded_inventory_fields if f[0] == "__builtin:death")
    assert fields.get("btn_respawn") == "true"

    # chat message handler
    seen: list[str] = []
    client.command_handler.register_chat_message_handler(lambda msg: seen.append(msg) or True)
    fake_server.push_chat("Server", "Welcome")
    _wait_for(lambda: seen == ["Welcome"])

    # time of day and speed updated
    fake_server.push_time_of_day(12000, 12.5)
    _wait_for(lambda: client.state._time_of_day > 0)
    assert client.state._time_speed == pytest.approx(12.5)

    # player list updates
    fake_server.push_update_player_list(0, ["a", "b"])
    _wait_for(lambda: client.state._connected_players == ["a", "b"])
    fake_server.push_update_player_list(1, ["c"])
    _wait_for(lambda: client.state._connected_players == ["a", "b", "c"])
    fake_server.push_update_player_list(2, ["b"])
    _wait_for(lambda: client.state._connected_players == ["a", "c"])

    # block data stored
    fake_server.push_blockdata(1, 2, 3, b"\x99\x88")
    _wait_for(lambda: (1, 2, 3) in client.state._blocks)

    # inbound split handling (PING)
    fake_server.push_split_ping()
    # no assertion beyond not crashing; ACKs are sent internally

    # outbound large packet is split
    big = b"x" * 2000
    assert client.connection.send_packet(big) is True
    _wait_for(lambda: fake_server.recorded_splits_outbound >= 3)

    # Explicit chat message -> server records CHAT_MESSAGE command
    client.send_chat_message("Hi there")
    _wait_for(lambda: ToServerCommand.CHAT_MESSAGE in fake_server.recorded_client_cmds)

    # Explicit gotblocks -> server records GOTBLOCKS
    client.send_gotblocks()
    _wait_for(lambda: ToServerCommand.GOTBLOCKS in fake_server.recorded_client_cmds)

    # Explicit formspec response -> server records inventory fields
    client.send_formspec_response("miney:code_form", {"lua": "return 1", "execution_id": "X1"})
    _wait_for(lambda: any(f[0] == "miney:code_form" for f in fake_server.recorded_inventory_fields))
    formname, fields = next(f for f in fake_server.recorded_inventory_fields if f[0] == "miney:code_form")
    assert fields.get("lua") == "return 1"
    assert fields.get("execution_id") == "X1"

    client.disconnect()
    assert client.state.connected is False


def test_connect_access_denied_raises(monkeypatch):
    server = FakeServer(deny=True)

    def socket_factory(*args, **kwargs):
        return FakeSocket(server)

    monkeypatch.setattr("miney.luanticlient.connection.socket.socket", socket_factory)

    client = LuantiClient(playername="Denied", password="pw")
    with pytest.raises(LuantiConnectionError):
        client.connect()
    client.disconnect()
