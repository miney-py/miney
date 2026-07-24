"""
Fetching games from ContentDB.

Luanti ships with no game at all, so a downloaded Luanti cannot create a world until one
is installed. This module is the narrowest thing that fixes that: it downloads one known
package and unpacks it under the game id the caller asked for.
"""
from __future__ import annotations

import logging
from pathlib import Path

from ..exceptions import MineyRunError
from .fetch import Fetcher, extract_single_dir, read_url

logger = logging.getLogger(__name__)

#: ContentDB moved from content.minetest.net along with the rename.
BASE_URL = "https://content.luanti.org"

#: The games Miney knows how to install, by the game id Luanti uses for them - which is
#: the directory name, and therefore what goes into ``world.mt``. Deliberately a short
#: list rather than a ContentDB search: a beginner picking a game from 300 results is a
#: worse experience than two that are known to work.
GAME_PACKAGES: dict[str, tuple[str, str]] = {
    "minetest_game": ("Luanti", "minetest_game"),
    "mineclone2": ("Wuzzy", "mineclone2"),
}

#: Human-facing names for those games. VoxeLibre renamed itself from MineClone2 to shed
#: the "Minecraft clone" image, but its game id - the ContentDB package, the directory in
#: ``games/``, the value ``--game`` takes and what lands in ``world.mt`` - is still
#: ``mineclone2``. So it is always shown as "VoxeLibre (mineclone2)": the name people use
#: now, next to the id everything technical still needs.
GAME_LABELS: dict[str, str] = {
    "minetest_game": "Minetest Game",
    "mineclone2": "VoxeLibre (mineclone2)",
}


def game_label(gameid: str) -> str:
    """
    A human-facing name for a game id.

    :param gameid: The game id, as used in ``--game`` and ``world.mt``.
    :return: The display name, or the id itself for a game with no registered label.
    """
    return GAME_LABELS.get(gameid, gameid)


#: The name a world gets when it is created for a game and the user named no world of
#: their own. The game id usually reads fine as a world name, but VoxeLibre's is
#: ``mineclone2``, so a world made for it is called ``VoxeLibre`` - the name the player
#: then sees in every message, not the old brand. World names must stay simple
#: identifiers, so this is the plain brand name, not the full ``VoxeLibre (mineclone2)``
#: label.
DEFAULT_WORLD_NAMES: dict[str, str] = {"mineclone2": "VoxeLibre"}


def default_world_name(gameid: str) -> str:
    """
    The world name to create for a game when the user did not name one.

    :param gameid: The game id.
    :return: A clean, on-brand world name; the game id itself for games without one.
    """
    return DEFAULT_WORLD_NAMES.get(gameid, gameid)


def package_url(author: str, package: str) -> str:
    """
    The download URL of a ContentDB package.

    :param author: ContentDB author name.
    :param package: ContentDB package name.
    :return: A URL that redirects to the current release ZIP.
    """
    return f"{BASE_URL}/packages/{author}/{package}/download/"


def install_game(gameid: str, games_dir: Path, fetch: Fetcher | None = None) -> Path:
    """
    Download a game and unpack it so Luanti can find it under its game id.

    :param gameid: The game id, which becomes the directory name.
    :param games_dir: Directory holding games. Created if it does not exist.
    :param fetch: Substitutable "read this URL" step. Defaults to a real request.
    :return: The installed game's directory.
    :raises MineyRunError: If the game is not one Miney knows, or the download or
        extraction failed.
    """
    known = GAME_PACKAGES.get(gameid)
    if known is None:
        raise MineyRunError(
            f"Miney does not know how to install the game '{gameid}'.\n"
            f"Known games: {', '.join(sorted(GAME_PACKAGES))}\n"
            "Install it yourself from https://content.luanti.org and try again."
        )

    author, package = known
    reader = fetch or read_url
    data = reader(package_url(author, package))
    logger.debug("Installing game %s into %s", gameid, games_dir)
    return extract_single_dir(data, games_dir, gameid)
