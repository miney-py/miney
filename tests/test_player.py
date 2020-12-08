import pytest
import miney
import math
from time import sleep


@pytest.fixture(scope="module")
def mt_player(mt: miney.Minetest):
    return mt.player[0]


def test_player(mt: miney.Minetest, mt_player: miney.Player):
    """
    Test player basics.

    :param mt: fixture
    :param mt_player: fixture
    :return: None
    """
    assert mt_player.is_online is True

    position = mt_player.position
    assert "x" in position
    assert "y" in position
    assert "z" in position

    mt_player.gravity = 0
    assert mt_player.gravity == 0

    # set fly or player will go into free fall
    mt_player.fly = True
    assert mt_player.fly

    mt_player.creative = True
    assert mt_player.creative

    mt_player.position = {"x": 12, "y": 8.5, "z": 12}
    sleep(0.1)  # give the value some time to get to the client
    position = mt_player.position
    assert 12.1 > position["x"] > 11.9
    assert 9 > position["y"] > 8
    assert 12.1 > position["z"] > 11.9

    mt_player.gravity = 0.8
    assert round(mt_player.gravity, 1) == 0.8

    mt_player.speed = 2.0
    assert mt_player.speed == 2.0

    mt_player.jump = 2.0
    assert mt_player.jump == 2.0

    look_vertical = mt_player.look_vertical
    assert 1.563 >= look_vertical >= -1.563  # 1.5620696544647 -1.5620696544647
    mt_player.look_vertical = 1.5620696544647
    sleep(0.01)  # give the value some time to get to the client
    assert 1.5622 > mt_player.look_vertical > 1.5616

    look_horizontal = mt_player.look_horizontal
    assert 6.25 > look_horizontal > 0  # 0 6.28
    mt_player.look_horizontal = math.pi
    sleep(0.1)  # give the value some time to get to the client
    assert 3.15 > mt_player.look_horizontal > 3.13

    mt_player.inventory.add("default:axe_wood")
