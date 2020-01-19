"""
Tests Minetest class' methods
"""
import socket
import miney
import pytest
import gc


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

# Deactivated for now. Focus on LAN and Singleplayer for now.
# def test_authentication(mt: miney.Minetest):
#     """
#     Test authentication.
#
#     :param mt: fixture
#     :return: None
#     """
#     # wrong playername
#     with pytest.raises(miney.AuthenticationError) as e:
#         mt_1 = miney.Minetest(playername="someuser", password="somepass")
#     # mt_1.close()
#
#     # wrong password
#     with pytest.raises(miney.AuthenticationError) as e:
#         mt_2 = miney.Minetest(password="somepass")
#     # del mt_2
#
#     # correct
#     mt_3 = miney.Minetest()
#     mt_3.close()
#     del mt_3
#     gc.collect()


def test_minetest(mt: miney.Minetest):
    """
    Test basic functionality.

    :param mt: fixture
    :return: None
    """
    assert str(mt) == '<minetest server "{}:{}">'.format("127.0.0.1", "29999")
    nodes = mt.node.nodes
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
    players = mt.players
    assert str(type(players)) == "<class 'list'>"
    assert "Player" in players, "You should join the server with playername \"Player\" for tests!"

    assert (mt.chat.send_to_all("Pytest is running...")) is None

    # get unknown player
    with pytest.raises(miney.PlayerInvalid) as e:
        mt.player("stupidname123")

    assert str(mt.player("Player")) == "<minetest player \"{}\">".format("Player")


def test_node_functions(mt: miney.Minetest):
    assert mt.node.set({"x": 12, "y": 80, "z": 12}, "default:wood") is None
