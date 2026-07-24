from __future__ import annotations
from pathlib import Path

from miney.env.paths import EnvPaths
from miney.env.state import WorldState, list_states, load_state, save_state


def test_save_then_load_roundtrip(tmp_path: Path):
    target = tmp_path / "run" / "castle" / "state.json"
    state = WorldState(name="castle", gameid="mineclone2", port=30001, server_pid=42)

    save_state(target, state)

    assert load_state(target) == state


def test_save_creates_missing_parent_directories(tmp_path: Path):
    target = tmp_path / "deep" / "nested" / "state.json"
    save_state(target, WorldState(name="w", gameid="minetest_game", port=30000))
    assert target.is_file()


def test_load_returns_none_for_missing_file(tmp_path: Path):
    assert load_state(tmp_path / "nope.json") is None


def test_load_returns_none_for_corrupt_file(tmp_path: Path):
    target = tmp_path / "state.json"
    target.write_text("{not json")
    assert load_state(target) is None


def test_load_returns_none_when_required_keys_are_missing(tmp_path: Path):
    target = tmp_path / "state.json"
    target.write_text('{"name": "w"}')
    assert load_state(target) is None


def test_list_states_returns_every_world(tmp_path: Path):
    paths = EnvPaths(root=tmp_path / ".miney")
    save_state(paths.state_file("alpha"), WorldState("alpha", "minetest_game", 30000))
    save_state(paths.state_file("beta"), WorldState("beta", "mineclone2", 30001))

    names = sorted(s.name for s in list_states(paths))

    assert names == ["alpha", "beta"]


def test_list_states_is_empty_without_a_run_directory(tmp_path: Path):
    assert list_states(EnvPaths(root=tmp_path / ".miney")) == []


def test_load_coerces_a_string_server_pid_to_none(tmp_path: Path):
    """
    A damaged state file is a cache of what we last did, not a source of truth --
    is_pid_alive(state.server_pid) later does `pid < 1`, which raises TypeError for a
    string. A bad pid should make us re-detect (None), not fail the whole file.
    """
    target = tmp_path / "state.json"
    target.write_text(
        '{"name": "w", "gameid": "minetest_game", "port": 30000, '
        '"server_pid": "not-a-number", "client_pid": "also-not-a-number"}'
    )

    state = load_state(target)

    assert state is not None
    assert state.server_pid is None
    assert state.client_pid is None
