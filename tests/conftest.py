"""
The place for fixtures
"""
import pytest
import miney


@pytest.fixture(scope="session")
def mt():
    # if not miney.is_miney_available():
    #     assert miney.run_miney_game(), "Minetest with mineysocket isn't running."

    mt = miney.Minetest()
    assert len(mt.player) >= 1
    return miney.Minetest()
