"""
Manages the state of the Luanti client.
"""
from typing import Any

from .constants import ClientState


class ClientStateHolder:
    """
    Holds all state variables for the Luanti client, separating state management
    from client logic and network communication.
    """

    def __init__(self):
        """Initializes the state holder with default values."""
        # Connection and authentication state
        self.state: int = ClientState.DISCONNECTED
        self.connected: bool = False
        self.authenticated: bool = False
        self.peer_id: int | None = None
        self.access_denied_reason: str | None = None
        self.access_denied_code: int | None = None

        # SRP authentication object
        self.srp_user: Any | None = None

        # Packet and command tracking
        self.sequence_number: int = 65500
        self.packets_sent: int = 0
        self.packets_received: int = 0
        self.last_processed_command_id: int | None = None

        # Game world state
        self.auto_respawn: bool = True
        self._player_position: dict[str, float] = {"x": 0.0, "y": 0.0, "z": 0.0}
        self._time_of_day: float = 0.0
        self._time_speed: float = 0.0
        self._connected_players: list[str] = []
        self._blocks: dict[tuple, bytes] = {}
        self._node_definitions: dict = {}
        self._has_node_definitions: bool = False
        self._node_definitions_raw: bytes | None = None

    def reset(self):
        """
        Resets the state to its initial values, typically for a new connection.
        """
        # Re-initialize all attributes to their default state
        self.__init__()
