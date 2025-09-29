
import json
import logging
import time
from unittest.mock import Mock, MagicMock

import pytest

from miney.callback import Callback
from miney.events import ChatMessageEvent


class MockClientState:
    def __init__(self, authenticated=True):
        self.authenticated = authenticated


class MockCommandHandler:
    def __init__(self):
        self._handlers = {}

    def register_formspec_handler(self, formname, handler):
        self._handlers[formname] = handler

    def get_handler(self, formname):
        return self._handlers.get(formname)


class MockLuantiClient:
    def __init__(self):
        self.state = MockClientState()
        self.command_handler = MockCommandHandler()
        self.sent_formspec_responses = []

    def send_formspec_response(self, formname, fields):
        self.sent_formspec_responses.append({"formname": formname, "fields": fields})
        return True

    def send_chat_message(self, message):
        return True


@pytest.fixture
def callback_env(monkeypatch):
    """Sets up a Callback instance with a mocked LuantiClient."""
    # Patch away the blocking wait in `_ensure_code_form_open`, which is not
    # relevant for most callback unit tests and slows down initialization.
    # This avoids a 2-second delay during test setup.
    monkeypatch.setattr("miney.callback.Callback._ensure_code_form_open", lambda self: None)

    mock_luanti_client = MockLuantiClient()
    mock_luanti = MagicMock()
    mock_luanti.luanti = mock_luanti_client

    callback = Callback(mock_luanti)

    # We must now manually simulate that the form is ready, since we patched
    # the method responsible for ensuring this.
    callback._code_form_shown = True

    yield callback, mock_luanti_client

    callback.shutdown()


def test_register_first_handler_sends_to_server(callback_env):
    # Arrange
    callback, mock_client = callback_env
    handler = Mock()

    # Act
    callback.register("chat_message", handler)

    # Assert
    assert len(mock_client.sent_formspec_responses) == 1
    payload = json.loads(mock_client.sent_formspec_responses[0]["fields"]["payload"])
    assert payload["action"] == "register"
    assert payload["events"] == ["chat_message"]


def test_register_second_handler_does_not_send(callback_env):
    # Arrange
    callback, mock_client = callback_env
    callback.register("chat_message", Mock())  # First registration
    mock_client.sent_formspec_responses.clear() # Clear initial send

    # Act
    callback.register("chat_message", Mock())  # Second registration

    # Assert
    assert len(mock_client.sent_formspec_responses) == 0


def test_unregister_last_handler_sends_to_server(callback_env):
    # Arrange
    callback, mock_client = callback_env
    handler = Mock()
    callback.register("chat_message", handler)
    mock_client.sent_formspec_responses.clear()

    # Act
    callback.unregister("chat_message", handler)

    # Assert
    assert len(mock_client.sent_formspec_responses) == 1
    payload = json.loads(mock_client.sent_formspec_responses[0]["fields"]["payload"])
    assert payload["action"] == "unregister"
    assert payload["events"] == ["chat_message"]


def test_dispatch_loop_calls_handler(callback_env):
    # Arrange
    callback, mock_client = callback_env
    handler_mock = Mock()
    callback.register("chat_message", handler_mock)
    
    # Simulate receiving data from the server
    handler = mock_client.command_handler.get_handler("miney:code_form")
    raw_event = {
        "event": "chat_message",
        "payload": {"name": "dev", "message": "testing"},
        "client_id": callback._client_id,
        "ts": time.time(),
    }

    # Act
    handler(json.dumps(raw_event))
    time.sleep(0.1) # Give dispatcher time to process

    # Assert
    handler_mock.assert_called_once()
    arg = handler_mock.call_args[0][0]
    assert isinstance(arg, ChatMessageEvent)
    assert arg.sender_name == "dev"


def test_handler_exception_is_caught(callback_env, caplog):
    # Arrange
    callback, mock_client = callback_env
    
    def failing_handler(event):
        raise ValueError("Something went wrong")

    callback.register("chat_message", failing_handler)
    
    handler = mock_client.command_handler.get_handler("miney:code_form")
    # Provide a valid payload for ChatMessageEvent
    raw_event = {
        "event": "chat_message",
        "payload": {"name": "test", "message": "test"},
        "client_id": callback._client_id,
    }

    # Act
    with caplog.at_level(logging.ERROR):
        handler(json.dumps(raw_event))
        time.sleep(0.1)  # Allow dispatch

    # Assert
    assert "Error in 'chat_message' handler" in caplog.text
    assert "ValueError: Something went wrong" in caplog.text


def test_shutdown_unregisters_all(callback_env):
    # Arrange
    callback, mock_client = callback_env
    callback.register("chat_message", Mock())
    callback.register("player_joins", Mock())
    callback.register_command("testcmd", Mock())
    mock_client.sent_formspec_responses.clear()

    # Act
    callback.shutdown()

    # Assert
    assert len(mock_client.sent_formspec_responses) == 3
    actions = {json.loads(resp["fields"]["payload"])["action"] for resp in mock_client.sent_formspec_responses}
    names = {
        json.loads(resp["fields"]["payload"]).get("name") for resp in mock_client.sent_formspec_responses
        if json.loads(resp["fields"]["payload"])["action"] == "unregister_chatcommand"
    }
    events = {
        json.loads(resp["fields"]["payload"])["events"][0] for resp in mock_client.sent_formspec_responses
        if json.loads(resp["fields"]["payload"])["action"] == "unregister"
    }
    
    assert "unregister_chatcommand" in actions
    assert "unregister" in actions
    assert "testcmd" in names
    assert "chat_message" in events
    assert "player_joins" in events


def test_register_unsupported_event_raises_value_error(callback_env):
    # Arrange
    callback, _ = callback_env

    # Act & Assert
    with pytest.raises(ValueError, match="Event 'invalid_event' is not supported"):
        callback.register("invalid_event", Mock())


def test_register_non_callable_raises_value_error(callback_env):
    # Arrange
    callback, _ = callback_env

    # Act & Assert
    with pytest.raises(ValueError, match="callback must be callable"):
        callback.register("chat_message", "not_a_function")


def test_send_without_authentication_logs_warning(callback_env, caplog):
    # Arrange
    callback, mock_client = callback_env
    mock_client.state.authenticated = False  # Simulate unauthenticated state

    # Act
    with caplog.at_level(logging.WARNING):
        callback.register("chat_message", Mock())

    # Assert
    assert "Cannot send callback registration: client not authenticated." in caplog.text


def test_handle_miney_callbacks_handles_server_error(callback_env, caplog):
    # Arrange
    callback, mock_client = callback_env
    handler = mock_client.command_handler.get_handler("miney:code_form")
    error_payload = {
        "error": "Something went wrong on the server",
        "code": "test_error"
    }

    # Act
    with caplog.at_level(logging.ERROR):
        handler(json.dumps(error_payload))

    # Assert
    assert "Callback error from server: Something went wrong on the server" in caplog.text


def test_handle_miney_callbacks_ignores_lua_result(callback_env):
    # Arrange
    callback, _ = callback_env
    lua_result_payload = {
        "result": "[true]",
        "execution_id": "some-id"
    }

    # Act
    # This should not raise an exception or put anything in the queue
    callback._handle_miney_callbacks(json.dumps(lua_result_payload))

    # Assert
    assert callback._events_queue.empty()
