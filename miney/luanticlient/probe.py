"""
A single UDP round-trip that tells a running Luanti server from a free port.

A bind test cannot do this: Luanti's server sets ``SO_REUSEADDR``, so the port stays
bindable while the server is using it, and on Windows an IPv6 wildcard bind does not even
reserve the IPv4 port. The only reliable signal on every platform is to speak the first
word of the protocol and see whether the server answers.
"""
from __future__ import annotations

import logging
import socket
import struct

logger = logging.getLogger(__name__)

#: Luanti's fixed protocol magic number, the first four bytes of every packet, also set
#: in :class:`~miney.luanticlient.client.Client`. It identifies the wire protocol and is
#: constant across Luanti versions.
PROTOCOL_ID = 0x4F457403


def probe_server(host: str, port: int, timeout: float = 1.0) -> bool:
    """
    Whether a Luanti server answers on a UDP port.

    Sends the connection handshake's first packet - the protocol id, peer id 0 and
    channel 0, the exact bytes Miney's own client opens a connection with - and waits
    for the server's reply, which begins with the protocol id echoed back.

    :param host: Host to probe, normally ``127.0.0.1``.
    :param port: UDP port to probe.
    :param timeout: Seconds to wait for a reply before giving up.
    :return: True if a Luanti server replied, False on timeout, a refused port, or any
        other socket error. Never raises: callers use this to decide whether a server is
        up, and "could not tell" means "not up".
    """
    packet = struct.pack(">I", PROTOCOL_ID) + struct.pack(">HB", 0, 0)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(packet, (host, port))
            data, _ = sock.recvfrom(1024)
    except OSError as error:
        logger.debug("Probe of %s:%s got no answer: %s", host, port, error)
        return False
    return len(data) >= 4 and struct.unpack(">I", data[0:4])[0] == PROTOCOL_ID
