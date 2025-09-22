from __future__ import annotations
from miney.luanticlient.srp import SRPClient


def test_srp_generate_first_and_start_auth_types():
    client = SRPClient(username="user", password="pw")

    # Cover helper that prepares SRP registration data
    out = client.generate_first_srp_data()
    assert isinstance(out, tuple) and len(out) == 3
    salt, verifier, is_empty = out
    assert isinstance(salt, (bytes, bytearray))
    assert isinstance(verifier, (bytes, bytearray))
    assert isinstance(is_empty, bool)

    # Start authentication flow produces user id and A
    who, A_bytes = client.start_authentication()
    assert who == "user"
    assert isinstance(A_bytes, (bytes, bytearray))
    assert len(A_bytes) > 0
