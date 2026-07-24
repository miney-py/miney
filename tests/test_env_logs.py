from __future__ import annotations
from pathlib import Path

import pytest

from miney.env.logs import follow, read_tail


def test_read_tail_returns_the_last_lines(tmp_path: Path):
    target = tmp_path / "server.log"
    target.write_text("\n".join(f"line {n}" for n in range(1, 11)) + "\n")

    assert read_tail(target, lines=3) == ["line 8", "line 9", "line 10"]


def test_read_tail_returns_everything_when_the_file_is_short(tmp_path: Path):
    target = tmp_path / "server.log"
    target.write_text("only\n")
    assert read_tail(target, lines=100) == ["only"]


def test_read_tail_returns_empty_for_a_missing_file(tmp_path: Path):
    assert read_tail(tmp_path / "nope.log") == []


def test_read_tail_survives_undecodable_bytes(tmp_path: Path):
    target = tmp_path / "server.log"
    target.write_bytes(b"good line\n\xff\xfe broken\n")
    assert len(read_tail(target)) == 2


def test_read_tail_does_not_swallow_unrelated_os_errors(tmp_path: Path, monkeypatch):
    target = tmp_path / "server.log"
    target.write_text("line\n")

    def raise_permission_error(*args, **kwargs):
        raise PermissionError("nope")

    monkeypatch.setattr(Path, "read_text", raise_permission_error)

    with pytest.raises(PermissionError):
        read_tail(target)


def test_read_tail_with_zero_lines_returns_an_empty_list(tmp_path: Path):
    target = tmp_path / "server.log"
    target.write_text("a\nb\nc\n")
    assert read_tail(target, lines=0) == []


def test_read_tail_with_negative_lines_raises_value_error(tmp_path: Path):
    target = tmp_path / "server.log"
    target.write_text("a\nb\nc\n")
    with pytest.raises(ValueError):
        read_tail(target, lines=-5)


def test_follow_yields_appended_lines(tmp_path: Path):
    target = tmp_path / "server.log"
    target.write_text("first\n")
    appended = {"done": False}

    def append_once() -> bool:
        if not appended["done"]:
            with target.open("a", encoding="utf-8") as handle:
                handle.write("second\n")
            appended["done"] = True
            return False
        return True

    collected = list(follow(target, interval=0, stop=append_once))

    assert collected == ["second"]


def test_follow_waits_for_a_file_that_does_not_exist_yet(tmp_path: Path):
    target = tmp_path / "later.log"
    calls = {"n": 0}

    def create_then_stop() -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            target.write_text("appeared\n")
            return False
        return True

    collected = list(follow(target, interval=0, stop=create_then_stop))

    assert collected == ["appeared"]


def test_follow_recovers_when_the_file_is_truncated(tmp_path: Path):
    target = tmp_path / "server.log"
    target.write_text("first\nsecond\n")
    state = {"step": 0}

    def truncate_then_stop() -> bool:
        state["step"] += 1
        if state["step"] == 1:
            target.write_text("new\n")
            return False
        return True

    collected = list(follow(target, interval=0, stop=truncate_then_stop))

    assert collected == ["new"]
