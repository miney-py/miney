from __future__ import annotations
from pathlib import Path

import pytest

from miney.env.discover import (
    MIN_VERSION,
    LuantiInstall,
    candidate_commands,
    discover,
    outdated_version,
    parse_version,
)
from miney.env.paths import EnvPaths

VERSION_OUTPUT = """Luanti 5.16.1 (Windows)
Using Irrlicht IrrlichtMt 1.9.0mt15
BUILD_TYPE=Release
RUN_IN_PLACE=1
USE_CURL=1
STATIC_SHAREDIR="."
"""


def test_parse_version_reads_the_first_line():
    assert parse_version(VERSION_OUTPUT) == (5, 16, 1)


def test_parse_version_accepts_the_old_product_name():
    assert parse_version("Minetest 5.7.0 (Linux)\n") == (5, 7, 0)


def test_parse_version_pads_a_two_part_version():
    assert parse_version("Luanti 5.8\n") == (5, 8, 0)


@pytest.mark.parametrize("text", ["", "something else entirely", "Luanti next-gen"])
def test_parse_version_returns_none_when_unparsable(text: str):
    assert parse_version(text) is None


def test_candidates_prefer_the_bundled_luanti(tmp_path: Path):
    paths = EnvPaths(root=tmp_path / ".miney")
    bundled = paths.luanti_dir / "bin" / "luanti.exe"
    bundled.parent.mkdir(parents=True)
    bundled.write_text("")

    first_command, first_source = candidate_commands(paths)[0]

    assert first_command == [str(bundled)]
    assert first_source == "bundled"


def test_candidates_find_a_macos_app_bundle(tmp_path: Path):
    # Official macOS releases ship a luanti.app bundle, not a bin/ tree. A Luanti
    # downloaded on macOS lives at luanti/luanti.app/Contents/MacOS/luanti and must be
    # rediscovered from there, or find_luanti fails after every download.
    paths = EnvPaths(root=tmp_path / ".miney")
    binary = paths.luanti_dir / "luanti.app" / "Contents" / "MacOS" / "luanti"
    binary.parent.mkdir(parents=True)
    binary.write_text("")

    first_command, first_source = candidate_commands(paths)[0]

    assert first_command == [str(binary)]
    assert first_source == "bundled"


def test_discover_returns_the_first_candidate_that_is_new_enough(tmp_path: Path):
    seen = []

    def runner(command):
        seen.append(command)
        if command[0] == "old":
            return "Luanti 5.6.0 (Linux)\n"
        if command[0] == "good":
            return VERSION_OUTPUT
        return None

    def candidates(_paths):
        return [(["missing"], "path"), (["old"], "path"), (["good"], "flatpak")]

    install = discover(None, runner=runner, candidates=candidates)

    assert install == LuantiInstall(launch=["good"], version=(5, 16, 1), source="flatpak")
    assert seen == [["missing"], ["old"], ["good"]]


def test_discover_returns_none_when_nothing_qualifies():
    def runner(command):
        return "Luanti 5.6.0 (Linux)\n"

    def candidates(_paths):
        return [(["old"], "path")]

    assert discover(None, runner=runner, candidates=candidates) is None


def test_outdated_version_reports_the_highest_too_old_install():
    def runner(command):
        return {"old": "Minetest 5.6.0 (Linux)\n", "older": "Minetest 5.5.0 (Linux)\n"}.get(
            command[0]
        )

    def candidates(_paths):
        return [(["older"], "path"), (["old"], "path")]

    assert outdated_version(None, runner=runner, candidates=candidates) == (5, 6, 0)


def test_outdated_version_is_none_when_a_usable_luanti_exists():
    def runner(command):
        return VERSION_OUTPUT

    def candidates(_paths):
        return [(["good"], "path")]

    assert outdated_version(None, runner=runner, candidates=candidates) is None


def test_outdated_version_is_none_when_nothing_runs():
    def candidates(_paths):
        return [(["missing"], "path")]

    assert outdated_version(None, runner=lambda command: None, candidates=candidates) is None


def test_minimum_version_matches_the_mod():
    mod_conf = Path(__file__).parent.parent / "mod_data" / "miney" / "mod.conf"
    declared = [
        line.split("=", 1)[1].strip()
        for line in mod_conf.read_text(encoding="utf-8").splitlines()
        if line.startswith("min_minetest_version")
    ]
    assert declared == [".".join(str(part) for part in MIN_VERSION)]
