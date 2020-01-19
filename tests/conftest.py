"""
The place for fixtures
"""

import pytest


@pytest.fixture(scope="session")
def mt():
    from miney import Minetest
    return Minetest(playername="Player")
