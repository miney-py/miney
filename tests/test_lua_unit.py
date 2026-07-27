from __future__ import annotations
import pytest

from conftest import FakeTransport
from miney.lua import Lua


def test_run_early_return_on_blank():
    lua = Lua(FakeTransport())
    assert lua.run("   ") is None


def test_an_answer_reaches_the_call_that_is_waiting():
    transport = FakeTransport()
    lua = Lua(transport)
    lua.pending_lua_results["123"] = None

    transport.deliver({"execution_id": "123", "result": 42})

    assert lua.pending_lua_results["123"] == {"execution_id": "123", "result": 42}


def test_a_record_without_an_execution_id_is_not_ours():
    """Events and acknowledgements travel on the same stream and belong to Callback."""
    transport = FakeTransport()
    lua = Lua(transport)

    transport.deliver({"event": "chat_message", "payload": {}})

    assert lua.pending_lua_results == {}


def test_mod_api_comes_from_the_transport():
    transport = FakeTransport(mod_api=11)
    assert Lua(transport).mod_api == 11


def test_get_node_info_builds_correct_lua(monkeypatch):
    calls: list[str] = []

    def fake_run(self, lua_code: str):
        calls.append(lua_code)
        return "OK"

    monkeypatch.setattr(Lua, "run", fake_run, raising=False)

    lua = Lua(FakeTransport())
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

    script = tmp_path / "script.lua"
    script.write_text("return 5", encoding="utf-8")

    assert Lua(FakeTransport()).run_file(str(script)) == "RAN"
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
