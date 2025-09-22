from __future__ import annotations
import json
import pathlib
import pytest
from typing import Callable, Dict, Any
from miney.lua import Lua


class _DummyState:
    """Lightweight state object emulating Luanti client's connection state."""
    def __init__(self, connected: bool = True, state_value: int = 999) -> None:
        self.connected = connected
        self.state = state_value


class _DummyCommandHandler:
    """Records formspec handlers so the mock can invoke them."""
    def __init__(self) -> None:
        self.handlers: Dict[str, Callable[[str], None]] = {}

    def register_formspec_handler(self, formname: str, handler: Callable[[str], None]) -> None:
        self.handlers[formname] = handler


class MockLuanti:
    """
    Minimal Luanti client stub to emulate server interaction for Lua.run().
    - Triggers form readiness when '/miney form' is sent
    - Sends back JSON or legacy formspec content upon send_formspec_response()
    """
    def __init__(self, playername: str = "Tester", mode: str = "success",
                 connected: bool = True, legacy: bool = False) -> None:
        self.playername = playername
        self.mode = mode
        self.legacy = legacy
        self.command_handler = _DummyCommandHandler()
        self.state = _DummyState(connected=connected, state_value=999)
        self.sent_messages: list[str] = []
        self.sent_fields: list[Dict[str, Any]] = []

    def send_chat_message(self, message: str) -> bool:
        self.sent_messages.append(message)
        # Simulate the initial formspec response so Lua.form_ready becomes True
        if message.strip() == "/miney form":
            handler = self.command_handler.handlers.get("miney:code_form")
            if handler:
                handler("null")  # JSON null -> marks form as ready, nothing stored
        return True

    def send_formspec_response(self, formname: str, fields: dict) -> bool:
        self.sent_fields.append(fields)
        handler = self.command_handler.handlers.get(formname)
        if not handler:
            raise AssertionError("No formspec handler registered for miney:code_form")

        exec_id = fields.get("execution_id")

        if self.mode == "noop":
            # Do not call the handler: simulates a server that never replies (timeout path).
            return True

        def _legacy_wrap(payload: str) -> str:
            return (
                "formspec_version[5]"
                "textarea[0,0;10,10;result;Label;" + payload + "]"
            )

        if self.mode == "success":
            payload = json.dumps({"execution_id": exec_id, "result": 42})
            handler(_legacy_wrap(payload) if self.legacy else payload)
            return True

        if self.mode == "error":
            payload = json.dumps({"execution_id": exec_id, "error": "boom"})
            handler(_legacy_wrap(payload) if self.legacy else payload)
            return True

        if self.mode == "perm_error":
            payload = json.dumps({
                "execution_id": exec_id,
                "error": "missing privilege 'miney'",
                "admins": ["admin1", "admin2"],
            })
            handler(_legacy_wrap(payload) if self.legacy else payload)
            return True

        raise ValueError(f"Unknown mock mode: {self.mode}")


def test_run_success_json_and_form_ready():
    client = MockLuanti(mode="success", legacy=False)
    lua = Lua(client)

    # run triggers: '/miney form' -> form_ready, then send_formspec_response -> result
    result = lua.run("return 1")
    assert result == 42
    assert "/miney form" in client.sent_messages[0]


def test_run_success_legacy_formspec():
    client = MockLuanti(mode="success", legacy=True)
    lua = Lua(client)

    result = lua.run("return 123")
    assert result == 42  # legacy pipeline still yields parsed JSON result


def test_run_permission_error_raises():
    client = MockLuanti(mode="perm_error", legacy=False)
    lua = Lua(client)

    with pytest.raises(Exception) as exc:
        lua.run("return 0")
    msg = str(exc.value)
    assert "privilege" in msg.lower()
    assert "/grant Tester miney" in msg


def test_run_regular_error_raises():
    client = MockLuanti(mode="error", legacy=False)
    lua = Lua(client)

    with pytest.raises(Exception) as exc:
        lua.run("return 0")
    assert "boom" in str(exc.value)


def test_run_timeout_raises_fast():
    client = MockLuanti(mode="noop", legacy=False)
    lua = Lua(client)

    with pytest.raises(Exception) as exc:
        lua.run("return 0", timeout=0.02)
    assert "Timeout waiting for Lua execution result" in str(exc.value)


def test_run_not_connected_raises():
    client = MockLuanti(mode="success", legacy=False, connected=False)
    lua = Lua(client)

    with pytest.raises(Exception) as exc:
        lua.run("return 0")
    assert "Not fully connected" in str(exc.value)


def test_get_node_info_builds_lua_for_specific_and_all():
    client = MockLuanti(mode="success", legacy=False)
    lua = Lua(client)

    lua.get_node_info("default:stone")
    lua.get_node_info()

    # The actual Lua code is sent via fields["lua"]; assert expected snippets present
    sent_codes = [entry["lua"] for entry in client.sent_fields]
    assert sent_codes[0] == 'return dump(minetest.registered_nodes["default:stone"])'
    assert "minetest.registered_nodes" in sent_codes[1]
    assert "count = " in sent_codes[1] or "count =" in sent_codes[1]
    assert "names =" in sent_codes[1]


def test_run_file_uses_contents(tmp_path: pathlib.Path):
    client = MockLuanti(mode="success", legacy=False)
    lua = Lua(client)

    script = tmp_path / "snippet.lua"
    script.write_text("return 5", encoding="utf-8")

    result = lua.run_file(str(script))
    assert result == 42  # server returns 42 regardless of input in this mock
    # Ensure the exact file content was sent to the server
    assert any(entry["lua"] == "return 5" for entry in client.sent_fields)
