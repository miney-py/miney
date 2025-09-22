from __future__ import annotations
import json
import pytest
from miney.lua import Lua


class DummyLuantiMinimal:
    def __init__(self) -> None:
        self.command_handler = None
        self.sent_messages: list[str] = []

    def send_chat_message(self, message: str) -> bool:
        self.sent_messages.append(message)
        return True


def test_send_command_calls_client():
    client = DummyLuantiMinimal()
    lua = Lua(client)
    ok = lua.send_command("status")
    assert ok is True
    assert client.sent_messages == ["/miney status"]


def test_run_early_return_on_blank():
    client = DummyLuantiMinimal()
    lua = Lua(client)
    assert lua.run("   ") is None


def test_handle_formspec_json_store():
    client = DummyLuantiMinimal()
    lua = Lua(client)
    exec_id = "123"
    lua.pending_lua_results[exec_id] = None
    payload = json.dumps({"execution_id": exec_id, "result": 42})
    lua._handle_miney_code_form(payload)
    assert lua.form_ready is True
    assert lua.pending_lua_results[exec_id] == {"execution_id": exec_id, "result": 42}


def test_handle_formspec_null_is_ignored():
    client = DummyLuantiMinimal()
    lua = Lua(client)
    lua._handle_miney_code_form("null")
    assert lua.form_ready is True  # still marks form as ready
    assert lua.pending_lua_results == {}  # no exec id registered, nothing stored


def test_parse_legacy_formspec_result_and_handle():
    client = DummyLuantiMinimal()
    lua = Lua(client)

    formspec = (
        'formspec_version[5]'
        'textarea[0,0;10,10;result;Label;'
        '{"execution_id":"abc","result":123}]'
    )
    # Direct parse
    extracted = lua._parse_legacy_formspec_result(formspec)
    assert extracted == '{"execution_id":"abc","result":123}'

    # Full handling storing result (register pending first)
    lua.pending_lua_results["abc"] = None
    lua._handle_miney_code_form(formspec)
    assert lua.pending_lua_results["abc"]["result"] == 123


def test_unescape_and_read_until_helpers():
    client = DummyLuantiMinimal()
    lua = Lua(client)

    text = r'abc\;def;ghi'
    sub, pos = lua._read_until_unescaped(text, 0, ';')
    assert sub == r'abc\;def'
    assert text[pos] == ';'

    s = r'\[a\;\]'
    assert lua._unescape_formspec(s) == '[a;]'


def test_get_node_info_builds_correct_lua(monkeypatch):
    calls: list[str] = []

    def fake_run(self, lua_code: str):
        calls.append(lua_code)
        return "OK"

    monkeypatch.setattr(Lua, "run", fake_run, raising=False)

    client = DummyLuantiMinimal()
    lua = Lua(client)

    lua.get_node_info("default:stone")
    lua.get_node_info()

    assert calls[0] == 'return dump(minetest.registered_nodes["default:stone"])'
    assert "minetest.registered_nodes" in calls[1]
    assert "count =" in calls[1]
    assert "names =" in calls[1]


def test_run_file_reads_and_passes_code(tmp_path, monkeypatch):
    captured: list[str] = []

    def fake_run(self, lua_code: str):
        captured.append(lua_code)
        return "RAN"

    monkeypatch.setattr(Lua, "run", fake_run, raising=False)

    p = tmp_path / "script.lua"
    p.write_text("return 5", encoding="utf-8")

    client = DummyLuantiMinimal()
    lua = Lua(client)
    result = lua.run_file(str(p))

    assert result == "RAN"
    assert captured == ["return 5"]


def test_dumps_raises_for_unknown_type(lua_for_dumps: Lua):
    class NotConvertible:
        pass

    with pytest.raises(ValueError):
        lua_for_dumps.dumps(NotConvertible())


def test_dumps_dict_with_bool_and_none_keys(lua_for_dumps: Lua):
    data = {True: 1, None: 2}
    dumped = lua_for_dumps.dumps(data)
    assert dumped == "{[true]=1, [nil]=2}"
