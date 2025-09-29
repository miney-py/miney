
import logging
from unittest.mock import MagicMock, Mock

import pytest

from miney.chat import Chat
from miney.player import Player


@pytest.fixture
def chat_instance():
    """Provides a Chat instance with a mocked Luanti parent."""
    mock_luanti = MagicMock()
    mock_luanti.lua = MagicMock()  # Mock the lua property
    # Mock dumps to just quote strings for simplicity in tests
    mock_luanti.lua.dumps.side_effect = lambda s: f'"{s}"'
    mock_luanti.callbacks = MagicMock()
    return Chat(mock_luanti)


def test_send_to_player_with_player_object(chat_instance):
    # Arrange
    # Configure the mocked lua.run to return valid data for Player.__init__
    chat_instance.lt.lua.run.return_value = {
        "password": "hash", "last_login": 123, "privileges": {}
    }
    mock_player = Player(chat_instance.lt, "testplayer")

    # Reset the mock after Player.__init__ has used it, so we can test
    # the call from send_to_player in isolation.
    chat_instance.lt.lua.run.reset_mock()

    # Act
    chat_instance.send_to_player(mock_player, "hello")

    # Assert
    chat_instance.lt.lua.run.assert_called_once_with(
        'return minetest.chat_send_player("testplayer", "hello")'
    )


def test_send_to_all_coerces_to_string(chat_instance, caplog):
    # Arrange
    message = 12345

    # Act
    with caplog.at_level(logging.WARNING):
        chat_instance.send_to_all(message)

    # Assert
    assert "Coercing chat message to string" in caplog.text
    chat_instance.lt.lua.run.assert_called_once_with('minetest.chat_send_all("12345")')


def test_send_to_player_raises_for_invalid_type(chat_instance):
    # Arrange
    invalid_player = 123

    # Act & Assert
    with pytest.raises(TypeError, match="Parameter 'player' must be str or Player"):
        chat_instance.send_to_player(invalid_player, "message")


def test_on_decorator_warns_for_non_chat_event(chat_instance, caplog):
    # Arrange
    event_name = "player_joins"

    # Act
    with caplog.at_level(logging.WARNING):
        decorator = chat_instance.on(event=event_name)
        # Decorator must be called to execute its logic
        @decorator
        def my_handler(event): pass

    # Assert
    assert f"Registering a handler for event '{event_name}' via Chat.on()" in caplog.text
    chat_instance.lt.callbacks.on.assert_called_once()
