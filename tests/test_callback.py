
import json
import logging
import time
from unittest.mock import Mock, MagicMock

import pytest

from miney import Point
from miney.callback import Callback
from miney.events import ChatCommandEvent, ChatMessageEvent


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


def test_each_handler_is_registered_separately(callback_env):
    """The server knows every handler by name, so a second one is news to it."""
    # Arrange
    callback, mock_client = callback_env
    first = callback.register("chat_message", Mock())
    mock_client.sent_formspec_responses.clear()

    # Act
    second = callback.register("chat_message", Mock())

    # Assert
    payload = json.loads(mock_client.sent_formspec_responses[0]["fields"]["payload"])
    assert payload["handler"] == second
    assert second != first


def test_unregister_last_handler_sends_to_server(callback_env):
    # Arrange
    callback, mock_client = callback_env
    handler = Mock()
    token = callback.register("chat_message", handler)
    mock_client.sent_formspec_responses.clear()

    # Act
    callback.unregister("chat_message", handler)

    # Assert
    assert len(mock_client.sent_formspec_responses) == 1
    payload = json.loads(mock_client.sent_formspec_responses[0]["fields"]["payload"])
    assert payload["action"] == "unregister"
    assert payload["events"] == ["chat_message"]
    assert payload["handler"] == token


def test_dispatch_loop_calls_handler(callback_env):
    # Arrange
    callback, mock_client = callback_env
    handler_mock = Mock()
    token = callback.register("chat_message", handler_mock)

    # Simulate receiving data from the server
    handler = mock_client.command_handler.get_handler("miney:code_form")
    raw_event = {
        "event": "chat_message",
        "payload": {"sender_name": "dev", "message": "testing"},
        "client_id": callback._client_id,
        "handlers": [token],
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


class CollectingHandler:
    """
    A callable object that is falsy while it is empty - a collector, a queue, a counter.

    Perfectly ordinary as a callback, and the reason `if handler:` is not the same
    question as `if handler is not None:`.
    """

    def __init__(self):
        self.calls = []

    def __call__(self, event):
        self.calls.append(event)

    def __len__(self):
        return len(self.calls)


def test_dispatch_loop_calls_a_command_handler(callback_env):
    # Arrange
    callback, mock_client = callback_env
    handler_mock = Mock()
    callback.register_command("testcmd", handler_mock)

    handler = mock_client.command_handler.get_handler("miney:code_form")
    raw_event = {
        "event": "chatcommand",
        "payload": {"command_name": "testcmd", "issuer": "dev", "param": "open"},
        "client_id": callback._client_id,
        "ts": time.time(),
    }

    # Act
    handler(json.dumps(raw_event))
    time.sleep(0.1)  # Give dispatcher time to process

    # Assert
    handler_mock.assert_called_once()
    arg = handler_mock.call_args[0][0]
    assert isinstance(arg, ChatCommandEvent)
    assert arg.command_name == "testcmd"
    assert arg.param == "open"


def test_a_command_handler_that_is_falsy_is_still_called(callback_env):
    """
    A handler is looked up by name, and finding one is not the same as it being truthy.

    An empty collector answers `False` to `if handler:` and the event was dropped in
    silence - and since it only fills up by being called, it stayed empty and stayed
    dropped, for the whole run.
    """
    # Arrange
    callback, mock_client = callback_env
    collector = CollectingHandler()
    callback.register_command("testcmd", collector)
    assert not collector, "the trap: an empty collector is falsy"

    handler = mock_client.command_handler.get_handler("miney:code_form")
    raw_event = {
        "event": "chatcommand",
        "payload": {"command_name": "testcmd", "issuer": "dev", "param": "open"},
        "client_id": callback._client_id,
        "ts": time.time(),
    }

    # Act
    handler(json.dumps(raw_event))
    time.sleep(0.1)

    # Assert
    assert len(collector.calls) == 1
    assert collector.calls[0].param == "open"


def test_handler_exception_is_caught(callback_env, caplog):
    # Arrange
    callback, mock_client = callback_env
    
    def failing_handler(event):
        raise ValueError("Something went wrong")

    token = callback.register("chat_message", failing_handler)

    handler = mock_client.command_handler.get_handler("miney:code_form")
    # Provide a valid payload for ChatMessageEvent
    raw_event = {
        "event": "chat_message",
        "payload": {"sender_name": "test", "message": "test"},
        "client_id": callback._client_id,
        "handlers": [token],
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


def test_register_sends_the_filter_to_the_server(callback_env):
    # Arrange
    callback, mock_client = callback_env

    # Act
    token = callback.register("chat_message", Mock(), {"sender_name": "Steve"})

    # Assert
    payload = json.loads(mock_client.sent_formspec_responses[0]["fields"]["payload"])
    assert payload["handler"] == token
    assert payload["filter"] == {"sender_name": "Steve"}


def test_register_without_a_filter_sends_none(callback_env):
    # Arrange
    callback, mock_client = callback_env

    # Act
    callback.register("chat_message", Mock())

    # Assert
    payload = json.loads(mock_client.sent_formspec_responses[0]["fields"]["payload"])
    assert "filter" not in payload


def test_register_with_an_unknown_filter_field_raises(callback_env):
    # Arrange
    callback, _ = callback_env

    # Act & Assert
    with pytest.raises(ValueError, match="has no field 'sender'"):
        callback.register("chat_message", Mock(), {"sender": "Steve"})


def test_a_filter_on_a_position_raises(callback_env):
    """
    A filter is answered with '==' on the server, so a position can never match one.

    It looks like the most natural filter there is - watch this spot - and before this
    raised, the mod read the table as a list of accepted values, found none, and rejected
    every event for the rest of the session without a word.
    """
    # Arrange
    callback, _ = callback_env

    # Act / Assert
    for value in ({"x": 1, "y": 2, "z": 3}, Point(1, 2, 3), [], {}):
        with pytest.raises(ValueError) as error:
            callback.register("node_dug", Mock(), {"pos": value})
        assert "string, a number, a boolean or a list" in str(error.value)


def test_a_filter_may_be_a_value_or_a_list_of_values(callback_env):
    # Arrange
    callback, mock_client = callback_env

    # Act
    callback.register("node_dug", Mock(), {"node_name": "mcl_core:dirt"})
    callback.register("node_dug", Mock(), {"node_name": ["mcl_core:dirt", "mcl_core:sand"]})
    callback.register("player_punched", Mock(), {"damage": 2})
    callback.register("player_leaves", Mock(), {"timed_out": True})

    # Assert
    assert len(mock_client.sent_formspec_responses) == 4


def test_unknown_filter_field_error_names_the_real_ones(callback_env):
    # Arrange
    callback, _ = callback_env

    # Act & Assert
    with pytest.raises(ValueError, match="It sends: message, sender_name"):
        callback.register("chat_message", Mock(), {"sender": "Steve"})


def test_two_handlers_keep_their_own_filters(callback_env):
    # Arrange
    callback, mock_client = callback_env

    # Act
    for_steve = callback.register("chat_message", Mock(), {"sender_name": "Steve"})
    for_alex = callback.register("chat_message", Mock(), {"sender_name": "Alex"})

    # Assert
    sent = [json.loads(r["fields"]["payload"]) for r in mock_client.sent_formspec_responses]
    assert {p["handler"]: p["filter"] for p in sent} == {
        for_steve: {"sender_name": "Steve"},
        for_alex: {"sender_name": "Alex"},
    }


def test_only_the_handler_the_event_names_runs(callback_env):
    """The mod applied the filters and said who the event is for."""
    # Arrange
    callback, mock_client = callback_env
    for_steve, for_alex = Mock(), Mock()
    steve_token = callback.register("chat_message", for_steve, {"sender_name": "Steve"})
    callback.register("chat_message", for_alex, {"sender_name": "Alex"})
    handler = mock_client.command_handler.get_handler("miney:code_form")

    # Act
    handler(json.dumps({
        "event": "chat_message",
        "payload": {"sender_name": "Steve", "message": "hi"},
        "client_id": callback._client_id,
        "handlers": [steve_token],
    }))
    time.sleep(0.1)

    # Assert
    for_steve.assert_called_once()
    for_alex.assert_not_called()


def test_an_event_for_two_handlers_reaches_both(callback_env):
    # Arrange
    callback, mock_client = callback_env
    first, second = Mock(), Mock()
    tokens = [
        callback.register("chat_message", first),
        callback.register("chat_message", second),
    ]
    handler = mock_client.command_handler.get_handler("miney:code_form")

    # Act
    handler(json.dumps({
        "event": "chat_message",
        "payload": {"sender_name": "Steve", "message": "hi"},
        "client_id": callback._client_id,
        "handlers": tokens,
    }))
    time.sleep(0.1)

    # Assert
    first.assert_called_once()
    second.assert_called_once()


def test_an_event_for_a_handler_that_is_gone_is_dropped(callback_env, caplog):
    """Unregistering and an event already on its way can cross in flight."""
    # Arrange
    callback, mock_client = callback_env
    handler_mock = Mock()
    token = callback.register("chat_message", handler_mock)
    callback.unregister("chat_message", token)
    handler = mock_client.command_handler.get_handler("miney:code_form")

    # Act
    with caplog.at_level(logging.DEBUG):
        handler(json.dumps({
            "event": "chat_message",
            "payload": {"sender_name": "Steve", "message": "hi"},
            "client_id": callback._client_id,
            "handlers": [token],
        }))
        time.sleep(0.1)

    # Assert
    handler_mock.assert_not_called()
    assert "which is gone" in caplog.text


def test_unregistering_one_handler_leaves_the_other(callback_env):
    # Arrange
    callback, mock_client = callback_env
    going, staying = Mock(), Mock()
    callback.register("chat_message", going)
    staying_token = callback.register("chat_message", staying)
    callback.unregister("chat_message", going)
    handler = mock_client.command_handler.get_handler("miney:code_form")

    # Act
    handler(json.dumps({
        "event": "chat_message",
        "payload": {"sender_name": "Steve", "message": "hi"},
        "client_id": callback._client_id,
        "handlers": [staying_token],
    }))
    time.sleep(0.1)

    # Assert
    staying.assert_called_once()
    going.assert_not_called()
