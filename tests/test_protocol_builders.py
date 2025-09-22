from __future__ import annotations
import struct

from miney.luanticlient.protocol import Protocol


def test_protocol_builders_and_parse_roundtrips():
    proto = Protocol(
        protocol_id=0x4D455449,  # arbitrary test id
        serialization_version=28,
        protocol_version=39,
        version_string="miney_v1.0",
    )

    # Basic command builders should return non-empty bytes
    assert isinstance(proto.create_init_payload("user", "pw"), bytes)
    assert isinstance(proto.create_init_command("user", "pw"), bytes)
    assert isinstance(proto.create_init2_command(), bytes)
    assert isinstance(proto.create_client_ready_command(), bytes)
    assert isinstance(proto.create_gotblocks_command(0, 0, 0), bytes)
    assert isinstance(proto.create_chat_message_command("Hello"), bytes)
    assert isinstance(proto.create_first_srp_command(b"\x00" * 16, b"\x01\x02", False), bytes)
    assert isinstance(proto.create_formspec_response_command("form", {"a": "b", "x": "y"}), bytes)
    assert isinstance(proto.create_srp_bytes_a_command(b"\x01\x02"), bytes)
    assert isinstance(proto.create_srp_bytes_m_command(b"\xAA"), bytes)

    # Reliable original packet -> parse back as 'reliable' with payload
    data = struct.pack(">H", 1234) + b"test"
    pkt = proto.create_reliable_original_packet(peer_id=0xBEEF, sequence_number=1, data=data)
    parsed = proto.parse(pkt)
    assert parsed is not None
    assert parsed.type == "reliable"
    assert hasattr(parsed.content, "payload")

    # Reliable split packet -> parse back; payload should not be an Original (no command_id)
    split_pkt = proto.create_reliable_split_packet(
        peer_id=0xBEEF, sequence_number=2, split_seqnum=42, total_chunks=2, chunk_num=0, chunk_data=b"\x99")
    parsed_split = proto.parse(split_pkt)
    assert parsed_split is not None
    assert parsed_split.type == "reliable"
    assert not hasattr(parsed_split.content.payload, "command_id")

    # ACK packet -> parse back as 'ack'
    ack = proto.create_ack_packet(peer_id=0xBEEF, channel=0, seqnum=7)
    parsed_ack = proto.parse(ack)
    assert parsed_ack is not None
    assert parsed_ack.type == "ack"

    # Disconnect/keep-alive builders return bytes (not parsed here)
    assert isinstance(proto.create_disconnect_packet(peer_id=0xBEEF), bytes)
    assert isinstance(proto.create_keep_alive_packet(peer_id=0xBEEF), bytes)


def test_protocol_parse_unframed_direct_command_bytes():
    proto = Protocol(
        protocol_id=0x4D455449,
        serialization_version=28,
        protocol_version=39,
        version_string="miney_v1.0",
    )
    parsed = proto.parse(b"\x00\x01garbage")
    assert parsed is not None
    assert parsed.type == "direct_command"
    assert parsed.content.command_id == 1
    assert parsed.content.data == b"garbage"
