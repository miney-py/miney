"""
miney - The python interface to minetest
"""
import os
import platform
import subprocess
import webbrowser
from .minetest import Minetest
from .player import Player
from .chat import Chat
from .node import Node
from .lua import Lua
from .exceptions import *

name = "miney"


def run_minetest(minetest_path: str = None, world_path: str = "Miney") -> None:
    """
    Run minetest with the miney game. Miney will look for the minetest executable in common places for itself,
    but it's also possible to provide the path as parameter or as environment variable 'MINETEST_BIN'.

    :param minetest_path: Path to the minetest executable
    :param world_path: Optional world path
    :return: None
    """
    if not minetest_path:
        if os.environ.get('MINETEST_BIN') and os.path.isfile(os.environ.get('MINETEST_BIN')):
            minetest_path = os.environ['MINETEST_BIN']
        else:
            if platform.system() == 'Windows':
                exe_name = "minetest.exe"
            else:
                exe_name = "minetest"

            # we have to guess the path
            possible_paths = [
                os.path.join(os.getcwd(), "Minetest", "bin"),
            ]
            for p in possible_paths:
                path = os.path.join(p, exe_name)
                if os.path.isfile(path):
                    minetest_path = p
                    break
                else:
                    raise MinetestRunError("Minetest was not found")
    if world_path == "miney":
        world_path = os.path.abspath(os.path.join(minetest_path, "..", "..", "worlds", "miney"))

    # todo: run_minetest - implementation for linux/macos
    # todo: run_minetest - ensure correct world creation if folder doesn't exists
    # todo: run_minetest - check for mineysocket

    subprocess.Popen(
        f"{minetest_path} "
        f"--go --world \"{world_path}\" --name Player --address \"\""
    )


def doc() -> None:
    """
    Open the documention in the webbrower. This is just a shortcut for IDLE or the python interactive console.

    :return: None
    """
    webbrowser.open("https://miney.readthedocs.io/en/latest/")
