from __future__ import annotations
from pathlib import Path

from miney.env.paths import EnvPaths, find_env


def test_paths_are_derived_from_root(tmp_path: Path):
    paths = EnvPaths(root=tmp_path / ".miney")
    assert paths.worlds_dir == tmp_path / ".miney" / "worlds"
    assert paths.run_dir == tmp_path / ".miney" / "run"
    assert paths.config_file == tmp_path / ".miney" / "luanti.conf"
    assert paths.client_pw == tmp_path / ".miney" / "client.pw"
    # Luanti and its games are shared, not under the project root. The autouse
    # _luanti_dir_in_tmp fixture points the default at tmp_path/"Luanti".
    assert paths.luanti_dir == tmp_path / "Luanti"
    assert paths.games_dir == tmp_path / "Luanti" / "games"
    assert paths.world_dir("castle") == tmp_path / ".miney" / "worlds" / "castle"
    assert paths.state_file("castle") == tmp_path / ".miney" / "run" / "castle" / "state.json"
    assert paths.log_file("castle") == tmp_path / ".miney" / "run" / "castle" / "server.log"


def test_find_env_walks_upward(tmp_path: Path):
    (tmp_path / ".miney").mkdir()
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)

    found = find_env(deep)

    assert found is not None
    assert found.root == tmp_path / ".miney"


def test_find_env_returns_none_when_absent(tmp_path: Path):
    assert find_env(tmp_path) is None


def test_find_env_ignores_a_file_named_miney(tmp_path: Path):
    (tmp_path / ".miney").write_text("not a directory")
    assert find_env(tmp_path) is None
