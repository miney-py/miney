from __future__ import annotations
import json
import pathlib
import pytest
from typing import Callable, Dict, Any
from miney.lua import Lua, REQUIRED_MOD_API


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
                 connected: bool = True, legacy: bool = False,
                 mod_api: int | None = REQUIRED_MOD_API) -> None:
        self.playername = playername
        self.mode = mode
        self.legacy = legacy
        #: What the mod claims to speak. None emulates a mod from before the handshake.
        self.mod_api = mod_api
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
                # A current mod answers the warm-up with its API number and nothing
                # else; one from before the handshake answers with JSON null.
                handler("null" if self.mod_api is None
                        else json.dumps({"mod_api": self.mod_api}))
        return True

    def send_formspec_response(self, formname: str, fields: dict) -> bool:
        self.sent_fields.append(fields)
        handler = self.command_handler.handlers.get(formname)
        if not handler:
            raise AssertionError("No formspec handler registered for miney:code_form")

        exec_id = fields.get("execution_id")

        # A request split over several submits is only run once the last piece has
        # arrived, the way the mod does it. Answering the first one would let run()
        # return while most of the code is still on the wire.
        if fields.get("part") and fields["part"] != fields.get("parts"):
            return True

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


def test_run_refuses_a_mod_from_before_the_handshake():
    """The failure this replaces was a nil index inside the user's own Lua."""
    client = MockLuanti(mode="success", legacy=False, mod_api=None)
    lua = Lua(client)

    with pytest.raises(Exception) as exc:
        lua.run("return 1")
    message = str(exc.value)
    assert "too old" in message
    assert "miney upgrade" in message
    assert not client.sent_fields  # refused before any code went out


def test_run_refuses_a_mod_that_is_behind():
    client = MockLuanti(mode="success", legacy=False, mod_api=REQUIRED_MOD_API - 1)
    lua = Lua(client)

    with pytest.raises(Exception) as exc:
        lua.run("return 1")
    assert f"speaks version {REQUIRED_MOD_API - 1}" in str(exc.value)


def test_run_accepts_a_newer_mod():
    """A mod ahead of us still speaks what we know, so it must not be refused."""
    client = MockLuanti(mode="success", legacy=False, mod_api=REQUIRED_MOD_API + 5)
    lua = Lua(client)

    assert lua.run("return 1") == 42


def test_run_sends_code_that_fits_in_one_submit():
    """
    The common call must not pay for the multipart machinery: one submit, and no
    part numbering for the mod to reassemble.
    """
    client = MockLuanti(mode="success", legacy=False)
    lua = Lua(client)

    assert lua.run("return 42") == 42
    assert len(client.sent_fields) == 1
    assert "part" not in client.sent_fields[0]


def test_run_splits_code_too_long_for_one_submit():
    """
    The server drops a submit over 640K without a word (``pkt_read_formspec_fields``
    in ``serverpackethandler.cpp``), so long code goes in several pieces instead.
    """
    from miney.lua import FORMSPEC_FIELD_LIMIT

    client = MockLuanti(mode="success", legacy=False)
    lua = Lua(client)

    code = "--" + "x" * (FORMSPEC_FIELD_LIMIT * 2)
    assert lua.run(code) == 42

    assert len(client.sent_fields) > 1
    # Every piece has to survive the trip on its own.
    for fields in client.sent_fields:
        payload = sum(
            len(name.encode()) + len(value.encode()) for name, value in fields.items()
        )
        assert payload < FORMSPEC_FIELD_LIMIT

    # Numbered from one so the mod can put them back in order, and complete.
    assert [f["part"] for f in client.sent_fields] == [
        str(i) for i in range(1, len(client.sent_fields) + 1)
    ]
    assert {f["parts"] for f in client.sent_fields} == {str(len(client.sent_fields))}
    assert {f["execution_id"] for f in client.sent_fields} == {
        client.sent_fields[0]["execution_id"]
    }
    assert "".join(f["lua"] for f in client.sent_fields) == code


def test_run_splits_without_cutting_a_character_in_half():
    """
    The limit counts bytes and the code is text: a piece that ends in the middle of a
    multi-byte character would arrive as two broken ones.
    """
    from miney.lua import FORMSPEC_FIELD_LIMIT

    client = MockLuanti(mode="success", legacy=False)
    lua = Lua(client)

    # Three bytes per character, so a naive slice at a byte boundary lands mid-character.
    code = "--" + "☃" * FORMSPEC_FIELD_LIMIT
    assert lua.run(code) == 42

    for fields in client.sent_fields:
        assert len(fields["lua"].encode()) < FORMSPEC_FIELD_LIMIT
    assert "".join(f["lua"] for f in client.sent_fields) == code


def test_run_refuses_code_over_the_absolute_maximum():
    """
    Splitting has an end: the mod refuses to collect more than MAX_LUA_SOURCE, so
    saying no here is better than filling the server's memory and timing out.
    """
    from miney.lua import MAX_LUA_SOURCE

    client = MockLuanti(mode="success", legacy=False)
    lua = Lua(client)

    with pytest.raises(Exception) as exc:
        lua.run("--" + "x" * (MAX_LUA_SOURCE + 1))
    assert "too long to send" in str(exc.value)
    assert not lua.pending_lua_results
    assert not client.sent_fields


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
