"""
Tests Minetest class' methods
"""
import socket
import miney
import pytest


def test_connection(mt: miney.Minetest):
    """
    Test connection with some missconfigurations.

    :param mt: fixture
    :return: None
    """
    # wrong server name
    with pytest.raises(socket.gaierror) as e:
        mt_fail = miney.Minetest("someunresolveableserver", "someuser", "somepass")

    # wrong port / apisocket unreachable or not running
    with pytest.raises((socket.timeout, ConnectionResetError)) as e:
        mt_fail = miney.Minetest(port=12345)


def test_send_corrupt_data(mt: miney.Minetest):
    """
    Send corrupt data, they shouldn't crash the server.

    :param mt: fixture
    :return: None
    """
    mt.connection.sendto(
        str.encode(
            "}s876" + "\n"
        ),
        ("127.0.0.1", 29999)
    )
    with pytest.raises(miney.exceptions.LuaError):
        mt.receive()


def test_minetest(mt: miney.Minetest):
    """
    Test basic functionality.

    :param mt: fixture
    :return: None
    """
    assert str(mt) == '<minetest server "{}:{}">'.format("127.0.0.1", "29999")
    nodes = mt.node.type
    assert "air" in nodes
    assert "default:stone" in nodes

    assert (mt.log("Pytest is running...")) is None

    settings = mt.settings
    assert "secure.trusted_mods" in settings
    assert "name" in settings

    assert 0 < mt.time_of_day < 1.1
    mt.time_of_day = 0.99
    assert 1 > mt.time_of_day > 0.95
    mt.time_of_day = 0.5
    assert 0.51 > mt.time_of_day > 0.49


def test_lua(mt: miney.Minetest):
    """
    Test running lua code.
    
    :param mt: fixture 
    :return: None
    """
    with pytest.raises(miney.LuaError) as e:
        mt.lua.run("thatshouldntworkatall")

    # multiple return values
    returnvalues = mt.lua.run(
        """
        mytable = {}
        mytable["var"] = 99
        return 12 , "test", {8, "9"}, mytable
        """
    )
    assert returnvalues == (12, 'test', [8, '9'], {'var': 99})


def test_players(mt: miney.Minetest):
    """
    Test player count and object creation.

    :param mt: fixture
    :return: None
    """
    players = mt.player
    assert str(type(players)) == "<class 'miney.player.PlayerIterable'>"
    assert len(players) >= 1, "You should join the server for tests!"

    assert (mt.chat.send_to_all("Pytest is running...")) is None

    # get unknown player
    with pytest.raises(AttributeError) as e:
        x = mt.player.stupidname123

    player = players[0]
    assert isinstance(player, miney.player.Player)
    assert len(player.name) > 0

    assert str(player) == "<minetest player \"{}\">".format(player.name)
