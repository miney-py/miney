import logging

from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from miney import luanti
from miney.luanticlient.exceptions import LuantiConnectionError


@patch("miney.luanti.LuantiClient")
@patch("miney.luanti.Lua")
@patch("miney.luanti.Chat")
@patch("miney.luanti.Nodes")
@patch("miney.luanti.ToolIterable")
@patch("miney.luanti.Callback")
def test_luanti_init_registration_fallback(
    MockCallback, MockToolIterable, MockNodes, MockChat, MockLua, MockLuantiClient
):
    # Arrange
    # First client instance fails with reason_code 1 (suggests registration)
    mock_client_1 = MagicMock()
    mock_client_1.connect.side_effect = LuantiConnectionError("Auth failed", reason_code=1)

    # Second client instance for registration succeeds
    mock_client_2 = MagicMock()
    mock_client_2.connect.return_value = True

    # Configure the mock to return the two instances sequentially
    MockLuantiClient.side_effect = [mock_client_1, mock_client_2]

    # Act
    lt = luanti.Luanti(server="test.server", playername="new_user", password="pwd")

    # Assert
    # Ensure two clients were created
    assert MockLuantiClient.call_count == 2
    
    # First client tried to connect normally
    mock_client_1.connect.assert_called_once_with()
    mock_client_1.disconnect.assert_called_once() # Should be disconnected cleanly

    # Second client tried to connect with registration flag
    mock_client_2.connect.assert_called_once_with(register=True)

    # Ensure the final object holds the second client
    assert lt.luanti == mock_client_2


@patch("miney.luanti.LuantiClient")
def test_luanti_init_raises_other_connection_errors(MockLuantiClient):
    # Arrange
    # Simulate a generic connection error (e.g., wrong password, not reason_code 1)
    mock_client = MagicMock()
    mock_client.connect.side_effect = LuantiConnectionError("Some other error", reason_code=2)
    MockLuantiClient.return_value = mock_client

    # Act & Assert
    with pytest.raises(LuantiConnectionError, match="Some other error"):
        luanti.Luanti()

    # Ensure it doesn't try to re-connect/register
    mock_client.connect.assert_called_once_with()


@patch("miney.luanti.LuantiClient")
@patch("miney.luanti.Lua")
@patch("miney.luanti.Chat")
@patch("miney.luanti.Nodes")
@patch("miney.luanti.ToolIterable")
@patch("miney.luanti.Callback")
def test_registering_a_new_player_is_not_a_warning(
    MockCallback, MockToolIterable, MockNodes, MockChat, MockLua, MockLuantiClient, caplog
):
    """
    Registering is what happens on every first connect, not something that went wrong.

    At warning level these lines reach stderr through logging's last-resort handler in
    any script that never configured logging - which is every beginner's script, and
    every run of "miney check". They stay, at info, for anyone who turns logging up.
    """
    denied = MagicMock()
    denied.connect.side_effect = LuantiConnectionError("Auth failed", reason_code=1)
    registered = MagicMock()
    registered.connect.return_value = True
    MockLuantiClient.side_effect = [denied, registered]

    with caplog.at_level(logging.DEBUG, logger="miney.luanti"):
        luanti.Luanti(server="test.server", playername="new_user", password="pwd")

    loud = [record for record in caplog.records if record.levelno >= logging.WARNING]
    assert not any(
        "regist" in record.message.lower() or "privilege" in record.message.lower()
        for record in loud
    )
    assert any(
        "registered" in record.message.lower() and record.levelno == logging.INFO
        for record in caplog.records
    )


@patch("miney.luanti.LuantiClient")
@patch("miney.luanti.Lua")
@patch("miney.luanti.Chat")
@patch("miney.luanti.Nodes")
@patch("miney.luanti.ToolIterable")
@patch("miney.luanti.Callback")
def test_a_session_watches_its_own_player_dying(
    MockCallback, MockToolIterable, MockNodes, MockChat, MockLua, MockLuantiClient
):
    """
    Miney's player has to come back after it died, so every session subscribes to its
    own death - and to nobody else's, or a script would resurrect the person playing.
    """
    lt = luanti.Luanti(server="test.server", playername="bot", password="pwd")

    registered = MockCallback.return_value.register.call_args_list
    assert ("player_dies", lt._get_up_again, {"player_name": "bot"}) in [
        call.args for call in registered
    ]


def test_a_dead_miney_player_gets_up_again():
    """
    The respawn goes through Lua: the client's answer to the death screen is dropped by
    the server whenever the mod has shown its own form in between, which is nearly
    always. Invisibility is put back on, because respawning re-skins the player.
    """
    lt = luanti.Luanti.__new__(luanti.Luanti)
    lt.playername = "bot"
    lt._invisible = True
    lt._lua = MagicMock()
    lt._lua.dumps.side_effect = lambda value: f'"{value}"'
    bot = MagicMock()

    with patch.object(luanti.Luanti, "players", new_callable=PropertyMock) as players:
        players.return_value = {"bot": bot}
        lt._get_up_again(object())

    code = lt._lua.run.call_args.args[0]
    assert '"bot"' in code and "respawn()" in code
    assert bot.invisible is True


def test_a_visible_miney_player_stays_visible_after_respawning():
    """A session started with invisible=False must not be hidden by a death."""
    lt = luanti.Luanti.__new__(luanti.Luanti)
    lt.playername = "bot"
    lt._invisible = False
    lt._lua = MagicMock()
    lt._lua.dumps.side_effect = lambda value: f'"{value}"'

    with patch.object(luanti.Luanti, "players", new_callable=PropertyMock) as players:
        lt._get_up_again(object())

    players.assert_not_called()
    assert "respawn()" in lt._lua.run.call_args.args[0]


def test_a_failing_respawn_does_not_reach_the_event_dispatcher(caplog):
    """
    This runs on the callback dispatcher thread. An exception there kills nothing but
    is invisible, so it is logged instead.
    """
    lt = luanti.Luanti.__new__(luanti.Luanti)
    lt.playername = "bot"
    lt._invisible = False
    lt._lua = MagicMock()
    lt._lua.dumps.return_value = '"bot"'
    lt._lua.run.side_effect = RuntimeError("server gone")

    with caplog.at_level(logging.ERROR, logger="miney.luanti"):
        lt._get_up_again(object())

    assert any("server gone" in record.getMessage() for record in caplog.records)
