"""Tests for miney.env.fetch."""
import http.client
import io
import urllib.request
import zipfile
from pathlib import Path

import pytest

from miney.env.fetch import extract_all, extract_single_dir, read_url
from miney.exceptions import MineyRunError


def _zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_extract_single_dir_renames_to_the_requested_name(tmp_path: Path):
    # ContentDB packages carry a top-level directory whose name is not guaranteed to
    # equal the game id the caller recorded in world.mt. The id wins.
    data = _zip({"VoxeLibre/game.conf": "title = VoxeLibre\n"})
    result = extract_single_dir(data, tmp_path, "mineclone2")
    assert result == tmp_path / "mineclone2"
    assert (result / "game.conf").read_text() == "title = VoxeLibre\n"


def test_extract_single_dir_replaces_an_existing_directory(tmp_path: Path):
    (tmp_path / "minetest_game").mkdir()
    (tmp_path / "minetest_game" / "stale.txt").write_text("old")
    data = _zip({"minetest_game/game.conf": "title = Minetest Game\n"})
    result = extract_single_dir(data, tmp_path, "minetest_game")
    assert not (result / "stale.txt").exists()
    assert (result / "game.conf").is_file()


def test_extract_single_dir_rejects_an_archive_with_several_roots(tmp_path: Path):
    data = _zip({"a/one.txt": "1", "b/two.txt": "2"})
    with pytest.raises(MineyRunError, match="one directory"):
        extract_single_dir(data, tmp_path, "whatever")


def test_extract_single_dir_handles_a_leading_dot_slash_prefix(tmp_path: Path):
    # `zip -r out.zip .` run from inside the packed directory stores every entry
    # with a leading './'. That must not be mistaken for a single shared root of
    # '.', which would make extract_single_dir operate on `target` itself.
    data = _zip({"./VoxeLibre/game.conf": "title = VoxeLibre\n"})
    result = extract_single_dir(data, tmp_path, "mineclone2")
    assert result == tmp_path / "mineclone2"
    assert (result / "game.conf").read_text() == "title = VoxeLibre\n"


def test_extract_single_dir_rejects_loose_files_with_a_dot_slash_prefix(tmp_path: Path):
    # Here `zip -r out.zip .` was run one level too deep: the archive has no single
    # top-level directory at all, just loose files each prefixed with './'. This must
    # be rejected -- not silently treated as a single root of '.' -- so it never
    # deletes and then tries to rename `target` into its own subdirectory.
    (tmp_path / "existing_game").mkdir()
    (tmp_path / "existing_game" / "keep.txt").write_text("do not delete me")
    data = _zip({"./game.conf": "title = Evil\n", "./textures/foo.png": "x"})
    with pytest.raises(MineyRunError, match="one directory"):
        extract_single_dir(data, tmp_path, "newgame")
    assert (tmp_path / "existing_game" / "keep.txt").read_text() == "do not delete me"


def test_extract_single_dir_rejects_a_path_that_escapes_the_target(tmp_path: Path):
    # A ZIP is untrusted input: an entry of ../../evil must not write outside target.
    data = _zip({"good/../../evil.txt": "x"})
    with pytest.raises(MineyRunError, match="unsafe path"):
        extract_single_dir(data, tmp_path, "good")


def test_extract_all_unpacks_everything_where_it_is_told(tmp_path: Path):
    data = _zip({"bin/luanti.exe": "binary", "builtin/init.lua": "-- lua"})
    result = extract_all(data, tmp_path / "luanti")
    assert result == tmp_path / "luanti"
    assert (result / "bin" / "luanti.exe").read_text() == "binary"
    assert (result / "builtin" / "init.lua").read_text() == "-- lua"


def test_extract_all_rejects_a_path_that_escapes_the_target(tmp_path: Path):
    data = _zip({"../evil.txt": "x"})
    with pytest.raises(MineyRunError, match="unsafe path"):
        extract_all(data, tmp_path / "luanti")


def test_extract_rejects_a_file_that_is_not_a_zip(tmp_path: Path):
    with pytest.raises(MineyRunError, match="not a ZIP"):
        extract_all(b"this is not a zip file", tmp_path / "out")


def test_read_url_reports_a_truncated_download(monkeypatch):
    # A transfer cut short mid-stream raises http.client.IncompleteRead, which is neither
    # an OSError nor a URLError. Left uncaught it reaches the CLI's catch-all and is
    # reported as a bug in Miney; it must be a MineyRunError telling the user to retry.
    def truncated(*args, **kwargs):
        raise http.client.IncompleteRead(partial=b"half a download")

    monkeypatch.setattr(urllib.request, "urlopen", truncated)
    with pytest.raises(MineyRunError, match="cut short"):
        read_url("https://example.invalid/luanti.zip")


def test_extract_all_reports_a_full_disk(tmp_path: Path, monkeypatch):
    # ENOSPC during extraction must name the disk, not surface as a raw OSError.
    data = _zip({"bin/luanti.exe": "binary"})

    def no_space(self, path):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(zipfile.ZipFile, "extractall", no_space)
    with pytest.raises(MineyRunError, match="disk is full"):
        extract_all(data, tmp_path / "luanti")


def test_extract_single_dir_reports_a_full_disk(tmp_path: Path, monkeypatch):
    data = _zip({"minetest_game/game.conf": "title = Minetest Game\n"})

    def no_space(self, path):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(zipfile.ZipFile, "extractall", no_space)
    with pytest.raises(MineyRunError, match="disk is full"):
        extract_single_dir(data, tmp_path, "minetest_game")
