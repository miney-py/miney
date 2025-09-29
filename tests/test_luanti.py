
from unittest.mock import MagicMock, patch

import pytest
from miney import luanti
from miney.luanticlient.exceptions import LuantiConnectionError


@patch("miney.luanti.LuantiClient")
@patch("miney.luanti.Lua")
@patch("miney.luanti.Chat")
@patch("miney.luanti.Nodes")
@patch("miney.luanti.ToolIterable")
@patch("miney.luanti.Callback")
def test_luanti_init_registration_fallback(
    MockCallback, MockToolIterable, MockNodes, MockChat, MockLua, MockLuantiClient
):
    # Arrange
    # First client instance fails with reason_code 1 (suggests registration)
    mock_client_1 = MagicMock()
    mock_client_1.connect.side_effect = LuantiConnectionError("Auth failed", reason_code=1)

    # Second client instance for registration succeeds
    mock_client_2 = MagicMock()
    mock_client_2.connect.return_value = True

    # Configure the mock to return the two instances sequentially
    MockLuantiClient.side_effect = [mock_client_1, mock_client_2]

    # Act
    lt = luanti.Luanti(server="test.server", playername="new_user", password="pwd")

    # Assert
    # Ensure two clients were created
    assert MockLuantiClient.call_count == 2
    
    # First client tried to connect normally
    mock_client_1.connect.assert_called_once_with()
    mock_client_1.disconnect.assert_called_once() # Should be disconnected cleanly

    # Second client tried to connect with registration flag
    mock_client_2.connect.assert_called_once_with(register=True)

    # Ensure the final object holds the second client
    assert lt.luanti == mock_client_2


@patch("miney.luanti.LuantiClient")
def test_luanti_init_raises_other_connection_errors(MockLuantiClient):
    # Arrange
    # Simulate a generic connection error (e.g., wrong password, not reason_code 1)
    mock_client = MagicMock()
    mock_client.connect.side_effect = LuantiConnectionError("Some other error", reason_code=2)
    MockLuantiClient.return_value = mock_client

    # Act & Assert
    with pytest.raises(LuantiConnectionError, match="Some other error"):
        luanti.Luanti()

    # Ensure it doesn't try to re-connect/register
    mock_client.connect.assert_called_once_with()
