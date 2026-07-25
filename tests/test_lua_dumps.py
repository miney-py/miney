from __future__ import annotations
import json
from miney.lua import Lua


def test_basic_types(lua_for_dumps: Lua):
    assert lua_for_dumps.dumps(None) == "nil"
    assert lua_for_dumps.dumps(True) == "true"
    assert lua_for_dumps.dumps(False) == "false"
    assert lua_for_dumps.dumps(42) == "42"
    assert lua_for_dumps.dumps(3.14) == "3.14"

    s = 'He said "hi"'
    dumped = lua_for_dumps.dumps(s)
    assert dumped == json.dumps(s, ensure_ascii=False)


def test_list_and_dict(lua_for_dumps: Lua):
    assert lua_for_dumps.dumps([1, "a", False]) == '{1, "a", false}'

    data = {"valid": 1, "invalid key": 2, 3: "numkey"}
    dumped = lua_for_dumps.dumps(data)
    assert dumped == '{valid=1, ["invalid key"]=2, [3]="numkey"}'


def test_iterable_conversion(lua_for_dumps: Lua):
    class KVIterable:
        def __iter__(self):
            yield "a", 1
            yield "b", 2

    dumped = lua_for_dumps.dumps(KVIterable())
    assert dumped == "{a=1, b=2}"


def test_nested_structures_and_escaping(lua_for_dumps):
    data = {
        "a": [1, {"b": "text with \"quotes\""}, True],
        "k v": {"inner key": None, 7: [False, 3.5]},
    }
    dumped = lua_for_dumps.dumps(data)
    # Struktur-Checks ohne strikte Reihenfolge
    assert '["k v"]' in dumped
    assert '"text with \\"quotes\\""' in dumped
    assert "true" in dumped and "false" in dumped and "nil" in dumped


def test_tuple_dump(lua_for_dumps: Lua):
    dumped = lua_for_dumps.dumps((1, "x"))
    assert dumped == '{1, "x"}'


def test_control_characters_use_lua_escapes(lua_for_dumps: Lua):
    """
    Lua has no ``\\u`` escape. JSON writes one for every control character, and the
    server answered such a string with a Lua syntax error.
    """
    assert lua_for_dumps.dumps("a\x00b") == '"a\\000b"'
    assert lua_for_dumps.dumps("a\x1bb") == '"a\\027b"'
    assert lua_for_dumps.dumps("a\x7fb") == '"a\\127b"'
    assert "\\u" not in lua_for_dumps.dumps("".join(chr(c) for c in range(32)))

    # The ones Lua names itself stay readable.
    assert lua_for_dumps.dumps("a\nb\tc\rd") == '"a\\nb\\tc\\rd"'

    # Three digits always, or "\1" before a literal "8" would read as "\18".
    assert lua_for_dumps.dumps("\x018") == '"\\0018"'


def test_backslashes_are_not_double_escaped(lua_for_dumps: Lua):
    assert lua_for_dumps.dumps("a\\b") == '"a\\\\b"'
    assert lua_for_dumps.dumps("\\u0000") == '"\\\\u0000"'


def test_non_ascii_passes_through(lua_for_dumps: Lua):
    assert lua_for_dumps.dumps("Höhle") == '"Höhle"'
