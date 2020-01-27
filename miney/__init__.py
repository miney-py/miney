"""
miney - The python interface to minetest
"""
import webbrowser
from .minetest import Minetest
from .player import Player
from .chat import Chat
from .node import Node
from .lua import Lua
from .exceptions import *

name = "miney"


def doc() -> None:
    """
    Open the documention in the webbrower. This is just a shortcut for IDLE or the python interactive console.

    :return: None
    """
    webbrowser.open("https://miney.readthedocs.io/en/latest/")
