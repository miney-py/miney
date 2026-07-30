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
- Brings media along, so a script has something to show and something to play in any
  game: `textures/miney_spark.png` and 47 sound effects in `sounds/`.
- Holds the sky a script sets for one player against a game that paints its own. VoxeLibre
  repaints every player about once a second; `sky.lua` hangs Miney's overlay at the end of
  that game's own filter chain, for that one player and only for the parts that were set.

## Bundled media

- `sounds/` - **Digital Audio** by **Kenney Vleugels**
  ([kenney.nl](https://kenney.nl/assets/digital-audio)), CC0. See `sounds/README.md` for
  the credit in full and for what was changed from the original pack.
- `textures/miney_spark.png` - the default particle, made for Miney and covered by the
  mod's own licence.

## Settings

- `miney_channel_budget_ms` (default `5`) - how much of one server step the mod may
  spend running commands before leaving the rest for the next one.
- `miney_log_level` (default `info`) - how much the mod writes to the server log.

## A warning worth repeating

This mod is code execution inside the server process, for anyone who can write into its
data directory. Install it on a world you would hand somebody the `/lua` command on.
