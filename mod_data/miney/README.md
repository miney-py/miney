# Miney Mod for Luanti

The server side of [Miney](https://github.com/miney-py/miney), the Python interface to
Luanti. It receives Lua code from Miney, runs it in a sandbox and sends the result back.

## How Miney reaches it

Through two files in this mod's own data directory, one pair per world. Nothing joins
the game, so no account, no password and no port are involved, and a singleplayer world
works exactly like a hosted one.

That also decides who may use it: whoever can write into the server's data directory can
run code on it, which is the same access the server process itself has. There is no
privilege to grant and none to withhold - a Luanti this mod is installed in is a Luanti
whose files you already trust everyone with.

Miney has to run on the same machine as the server. A world on another computer is out
of reach, because a file on your disk is not on theirs.

## Features

- Runs Lua for Miney, one sandbox per session, with an instruction budget so a loop that
  never ends does not take the server with it.
- Delivers the events and chat commands a Python script registers.
- Cleans up after a session that stops answering: its timers are cancelled and its chat
  commands unregistered, so a killed script leaves nothing behind.

## Settings

- `miney_channel_budget_ms` (default `5`) - how much of one server step the mod may
  spend running commands before leaving the rest for the next one.
- `miney_log_level` (default `info`) - how much the mod writes to the server log.

## A warning worth repeating

This mod is code execution inside the server process, for anyone who can write into its
data directory. Install it on a world you would hand somebody the `/lua` command on.
