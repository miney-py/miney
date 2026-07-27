"""
Storage against a fake server: a dict standing in for the world's key-value store.
"""
import json
from unittest.mock import MagicMock

import pytest

from miney.lua import Lua
from miney.storage import Storage


class FakeStorage:
    """
    The half of the Lua side that Storage actually talks to.

    Only four snippets ever reach the server, so they are matched rather than parsed.
    Luanti's own rules are kept: an empty value deletes, and an empty store answers
    ``to_table().fields`` with nil.
    """

    def __init__(self, fields: dict[str, str] | None = None):
        self.fields = dict(fields or {})
        self.calls: list[str] = []

    def run(self, code: str, timeout=None, execution_id=None, wait=True):
        self.calls.append(code)
        if code == "return storage:to_table().fields":
            return dict(self.fields) or None
        if code == "storage:from_table(nil) return true":
            self.fields.clear()
            return True
        if code.startswith("storage:set_string("):
            key, value = json.loads("[" + code[len("storage:set_string("):code.rindex(")")] + "]")
            self.fields[key] = value
            return True
        if code.startswith("local key = "):
            key = json.loads(code[len("local key = "):code.index(" if not")])
            if key not in self.fields:
                return False
            del self.fields[key]
            return True
        raise AssertionError(f"unexpected Lua: {code!r}")


@pytest.fixture
def storage() -> Storage:
    luanti = MagicMock()
    fake = FakeStorage({"home": "10,20,30"})
    luanti.lua = MagicMock()
    luanti.lua.run.side_effect = fake.run
    luanti.lua.dumps.side_effect = Lua.dumps.__get__(luanti.lua)
    store = Storage(luanti)
    store.fake = fake
    return store


def test_reads_and_writes_like_a_dict(storage: Storage):
    assert storage["home"] == "10,20,30"
    storage["spawn"] = "0,0,0"
    assert storage["spawn"] == "0,0,0"
    assert storage.fake.fields["spawn"] == "0,0,0"


def test_missing_key_raises_key_error(storage: Storage):
    with pytest.raises(KeyError):
        storage["nope"]
    with pytest.raises(KeyError):
        del storage["nope"]
    assert storage.get("nope") is None
    assert storage.get("nope", "fallback") == "fallback"


def test_mapping_protocol(storage: Storage):
    storage["spawn"] = "0,0,0"
    assert "home" in storage and "nope" not in storage
    assert len(storage) == 2
    assert sorted(storage) == ["home", "spawn"]
    assert dict(storage.items()) == {"home": "10,20,30", "spawn": "0,0,0"}
    assert sorted(storage.keys()) == ["home", "spawn"]
    assert sorted(storage.values()) == ["0,0,0", "10,20,30"]

    storage.update({"a": "1"})
    assert storage.pop("a") == "1"
    assert storage.setdefault("home", "unused") == "10,20,30"

    del storage["home"]
    assert "home" not in storage


def test_clear_uses_a_single_call(storage: Storage):
    storage["a"] = "1"
    storage.fake.calls.clear()
    storage.clear()
    assert storage.fake.calls == ["storage:from_table(nil) return true"]
    assert len(storage) == 0


def test_reading_takes_one_call_per_operation(storage: Storage):
    """``to_table`` returns everything, so listing must not cost one call per key."""
    storage["a"] = "1"
    storage["b"] = "2"
    storage.fake.calls.clear()
    dict(storage.items())
    assert len(storage.fake.calls) == 1


def test_values_must_be_strings(storage: Storage):
    with pytest.raises(TypeError, match="Storage values are strings"):
        storage["visits"] = 42
    with pytest.raises(TypeError, match="json.dumps"):
        storage["seen"] = ["Steve"]
    # The message points at the way out, and that way works.
    storage["visits"] = str(42)
    storage["seen"] = json.dumps(["Steve"])
    assert int(storage["visits"]) == 42
    assert json.loads(storage["seen"]) == ["Steve"]


def test_empty_value_is_refused_instead_of_deleting(storage: Storage):
    """Luanti deletes a key that is set to "". Silently doing that would be a trap."""
    with pytest.raises(ValueError, match="del lt.storage"):
        storage["home"] = ""
    assert storage["home"] == "10,20,30"


def test_keys_must_be_non_empty_strings(storage: Storage):
    with pytest.raises(TypeError, match="Storage keys are strings"):
        storage[7] = "x"
    with pytest.raises(ValueError, match="cannot be empty"):
        storage[""] = "x"


def test_empty_store_reads_as_empty(storage: Storage):
    storage.clear()
    assert len(storage) == 0
    assert dict(storage) == {}
    assert list(storage) == []


def test_values_with_lua_syntax_survive(storage: Storage):
    """Everything crossing into Lua goes through dumps, quotes and backslashes included."""
    tricky = 'He said "hi"\\ and \n stopped'
    storage["tricky"] = tricky
    assert storage["tricky"] == tricky


def test_repr_shows_content_while_it_is_small(storage: Storage):
    assert repr(storage) == "<Luanti Storage: {'home': '10,20,30'}>"
    for index in range(6):
        storage[f"k{index}"] = "v"
    assert repr(storage) == "<Luanti Storage: 7 keys>"
