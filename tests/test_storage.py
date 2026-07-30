"""
Storage against a fake server: a dict standing in for the world's key-value store.
"""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from miney.exceptions import PlayerOffline
from miney.lua import Lua
from miney.storage import PlayerStorage, Storage


class FakeStorage:
    """
    The half of the Lua side that a store actually talks to.

    Only a handful of snippets ever reach the server, so they are matched rather than
    parsed. Luanti's own rules are kept: an empty value deletes, and an empty store
    answers ``to_table().fields`` with nil.

    Every call arrives wrapped in the same header, which binds the store to ``meta`` and
    answers with a sentinel when there is no store to bind - that is how a player who
    left is told apart from a store that is simply empty.
    """

    #: What the wrapper answers for a store that is not there.
    ABSENT = "\0absent"

    def __init__(self, fields: dict[str, str] | None = None, there: bool = True):
        self.fields = dict(fields or {})
        self.there = there
        self.calls: list[str] = []

    def run(self, code: str, timeout=None, execution_id=None, wait=True):
        self.calls.append(code)
        head, _, body = code.partition('absent" end ')
        assert body, f"missing the store header: {code!r}"
        if not self.there:
            return self.ABSENT

        if body == "return meta:to_table().fields":
            return dict(self.fields) or None
        if body == "meta:from_table(nil) return true":
            self.fields.clear()
            return True
        if body.startswith("meta:set_string("):
            key, value = json.loads(
                "[" + body[len("meta:set_string("):body.rindex(")")] + "]")
            self.fields[key] = value
            return True
        if body.startswith("local key = "):
            key = json.loads(body[len("local key = "):body.index(" if not")])
            if key not in self.fields:
                return False
            del self.fields[key]
            return True
        if body.startswith("for _, key in ipairs({"):
            keys = body[body.index("({") + 1:body.index("}) do") + 1]
            for key in json.loads(keys.replace("{", "[").replace("}", "]")):
                self.fields.pop(key, None)
            return True
        raise AssertionError(f"unexpected Lua: {body!r}")


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
    assert len(storage.fake.calls) == 1
    assert storage.fake.calls[0].endswith("meta:from_table(nil) return true")
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


# --- one player's store ------------------------------------------------------------
#
# The same class underneath, with two differences that matter: the table it writes into
# belongs to the game as well, so everything is filed under a prefix, and the player can
# walk away, so a call can find nothing to write to.

#: What a game and Miney itself already keep about a player. Nothing here is ours.
FOREIGN = {
    "gamemode": "survival",
    "miney:before_hold": "return {gravity = 1}",
    "mcl_hunger:hunger": "20",
}


def _player_store(fields: dict[str, str] | None = None, there: bool = True):
    """A :class:`PlayerStorage` for "Steve", over a fake store."""
    luanti = MagicMock()
    fake = FakeStorage(fields, there=there)
    luanti.lua = MagicMock()
    luanti.lua.run.side_effect = fake.run
    luanti.lua.dumps.side_effect = Lua.dumps.__get__(luanti.lua)

    player = SimpleNamespace(lt=luanti, name="Steve")
    store = PlayerStorage(player)
    store.fake = fake
    return store


@pytest.fixture
def player_storage() -> PlayerStorage:
    return _player_store(dict(FOREIGN))


def test_player_storage_reads_and_writes_like_a_dict(player_storage):
    player_storage["home"] = "10,20,30"
    assert player_storage["home"] == "10,20,30"
    assert "home" in player_storage
    del player_storage["home"]
    assert "home" not in player_storage


def test_a_players_keys_are_filed_under_a_prefix(player_storage):
    player_storage["home"] = "10,20,30"
    assert player_storage.fake.fields["miney:data:home"] == "10,20,30"
    assert "home" not in player_storage.fake.fields, "a bare key would collide with a game"


def test_the_games_own_keys_stay_invisible(player_storage):
    player_storage["home"] = "10,20,30"

    assert list(player_storage) == ["home"]
    assert len(player_storage) == 1
    assert "gamemode" not in player_storage
    with pytest.raises(KeyError):
        player_storage["gamemode"]


def test_clear_leaves_everything_that_is_not_ours(player_storage):
    player_storage["home"] = "10,20,30"
    player_storage["deaths"] = "3"
    player_storage.clear()

    assert len(player_storage) == 0
    assert player_storage.fake.fields == FOREIGN, "the game's notes were collateral damage"


def test_clear_costs_one_call(player_storage):
    player_storage["home"] = "10,20,30"
    player_storage["deaths"] = "3"
    player_storage.fake.calls.clear()
    player_storage.clear()

    assert len(player_storage.fake.calls) == 2, "one to list ours, one to delete them"


def test_clear_with_nothing_stored_deletes_nothing(player_storage):
    player_storage.fake.calls.clear()
    player_storage.clear()

    assert player_storage.fake.fields == FOREIGN
    assert all("set_string" not in call for call in player_storage.fake.calls)


def test_a_players_messages_name_the_players_store(player_storage):
    with pytest.raises(ValueError, match=r"del player\.storage"):
        player_storage["home"] = ""
    with pytest.raises(TypeError, match=r"player\.storage\[str\(7\)\]"):
        player_storage[7] = "x"


def test_a_player_who_left_is_said_out_loud():
    store = _player_store(there=False)

    with pytest.raises(PlayerOffline, match="Steve"):
        store["home"] = "10,20,30"
    with pytest.raises(PlayerOffline, match="Steve"):
        len(store)
    with pytest.raises(PlayerOffline, match="Steve"):
        store.clear()


def test_a_players_repr_names_the_player(player_storage):
    player_storage["home"] = "10,20,30"
    assert repr(player_storage) == '<Player "Steve" storage: {\'home\': \'10,20,30\'}>'


def test_repr_shows_content_while_it_is_small(storage: Storage):
    assert repr(storage) == "<Luanti Storage: {'home': '10,20,30'}>"
    for index in range(6):
        storage[f"k{index}"] = "v"
    assert repr(storage) == "<Luanti Storage: 7 keys>"
