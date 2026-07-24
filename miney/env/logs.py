"""
Reading the server log.

Lines always come from the file Luanti writes with ``--logfile``, never from a process's
standard output. The processes are detached, so there is no pipe to read; and Luanti's
console logging on Windows is unreliable, while the log file is written the same way
everywhere. It also means the log of a server started by an earlier script run, or from
another terminal, can still be read.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Iterator


def read_tail(path: Path, lines: int = 200) -> list[str]:
    """
    The last lines of a log file.

    :param path: The log file.
    :param lines: How many lines to return at most. 0 returns an empty list.
    :return: The lines, without trailing newlines. Empty if the file does not exist.
    :raises ValueError: If ``lines`` is negative.
    """
    if lines < 0:
        raise ValueError(
            f"lines must be 0 or greater, got {lines}. Use 0 to read no lines, "
            "or a positive number for the last N lines."
        )
    if lines == 0:
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return []
    return text.splitlines()[-lines:]


def follow(
    path: Path,
    interval: float = 0.5,
    stop: Callable[[], bool] | None = None,
) -> Iterator[str]:
    """
    Yield lines as they are appended, like ``tail -f``.

    Implemented by polling rather than by calling ``tail``, which does not exist on
    Windows. A file that does not exist yet is waited for rather than treated as an
    error, so this can be started before the server has written anything. If the file
    is replaced or truncated (``miney start`` restarting a server against the same
    ``--logfile`` path) while this is running, it is detected and reading resumes from
    the start of the new content instead of going silent.

    :param path: The log file.
    :param interval: Seconds to wait between checks.
    :param stop: Called between checks; returning True ends the loop. The command line
        passes nothing and relies on Ctrl+C.
    :return: An iterator yielding each new line as it is appended, without trailing
        newlines. Never ends on its own; only ``stop`` returning True ends it.
    """
    position = path.stat().st_size if path.is_file() else 0
    while True:
        if path.is_file():
            current_size = path.stat().st_size
            if current_size < position:
                # The file got shorter than what we already read: it was replaced or
                # truncated, most likely by a server restart. Start over.
                position = 0
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(position)
                chunk = handle.read()
                position = handle.tell()
            for line in chunk.splitlines():
                yield line
        if stop is not None:
            if stop():
                return
        if interval:
            time.sleep(interval)
