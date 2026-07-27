# TODO

A list of things i'm planning to do. There will be no fixed timeline.

Feel free to contribute!

## General

* [x] automate pypi and contentdb release

## API

* [ ] Convenience aliases for `Player.move()`: `teleport()`, `look_at()`, `fly_to()`, `turn()`
  * Thin wrappers around `move()`, not separate implementations
  * Each one documents the equivalent `move()` call, so the alias teaches the general function
* [ ] Callbacks
  * [x] Basic API and some callbacks implemented
  * [x] Implement more "register_on_..." functions
  * [ ] `player_near` - fire when a player comes within a radius of a position (see below)
* [ ] Asyncio
* [x] Miney Proxy
  * Solved differently, and better: a world on this computer is reached through two
    append-only files in Luanti's `mod_data` directory instead of a player account.
    No account, no port, no password, and it works in a singleplayer world started
    from the Luanti menu - which no client connection can reach at all.
* [x] Drop `miney/luanticlient/`
  * ~1800 lines of UDP, SRP and packet code, gone with the `miney` privilege, the
    formspec transport and the split-request assembly. It bought 30 ms per command;
    what a script waits for is answers, not commands.
* [ ] Reach a server on another machine again, properly
  * The file channel needs the server on this disk. A small relay - a process next to
    the server that speaks the same JSON lines over a socket - would restore it without
    bringing a hand-written client protocol back.
  * Not urgent. Nobody has asked, and every use Miney has today is local.
* [ ] Batch reads
  * Every read is its own round trip, so 50 entities × 2 properties is 100 server steps.
    One Lua chunk could gather all of it in one. The writing half already pipelines;
    this is the other half, and it is what an agent driving many entities needs.
  * Has to stay off the beginner's path: no new concept in `lt.players[...]`.
* [ ] Compact the channel logs during a session
  * Both are emptied only when the server starts, so a long-running session grows them
    without bound - fine for a lesson, not for a research run generating events for
    days. Needs a two-way handshake; either side truncating a file the other is reading
    is a race a poll interval only usually wins. See the `ponytail:` note in
    `mod_data/miney/channel.lua`.
* [x] Send without waiting
  * Calls with nothing to return do not wait; the next call that needs an answer is the
    barrier, and `disconnect()` flushes. 400 nodes in a plain `for` loop: 12.2 s → 0.06 s.
    No new concept on the surface, `lua.run(wait=False)` and `lua.flush()` underneath.
* [ ] Mesecons: Add a python script processor that executes python code.
* Python driven mobs?

## Presentation

Everything here is one or two lines of Luanti Lua today, written by hand through
`lt.lua.run()` with manual `lua.dumps()` quoting. `demo/worldsmith/worldsmith/fx.py` is
the workaround for all of it; the goal is to delete that file.

Each entry is one class, reached through a property, never constructed by the user.
Per-player things hang off `Player`, world-wide things off `Luanti`.

* [x] `Hud` - `player.hud`, wraps `player:hud_add/hud_change/hud_remove`
  * A message on screen is the missing half of `chat.send_to_player()`: chat scrolls away,
    a HUD element stays until you take it down
  * `player.hud.text("Welcome!", position=...)` returns a handle with `.change()` / `.remove()`;
    `player.hud.clear()` takes everything down that this session put up
  * Text first. Images, statbars and the rest only if a lesson needs them
  * Beginner trap for the docstring: the element belongs to that player alone, and it
    survives the script that made it unless something removes it
* [ ] `Sky` - `player.sky`, wraps `set_sky` / `set_sun` / `set_moon` / `set_stars` / `set_clouds`
  * Properties, not methods: `player.sky.color = "#101040"`, `player.sky.clouds = False`,
    `player.sky.sun = False`
  * `player.sky.reset()` puts the normal sky back - a script that darkens the sky and exits
    leaves a player in permanent night otherwise
  * Names the trap: darkening the sky summons zombies in VoxeLibre. See `immortal` below
* [ ] `Particles` - `lt.particles`, wraps `minetest.add_particlespawner` / `add_particle`
  * `lt.particles.spawn(Point(...), texture=..., amount=20, time=2)` for a burst,
    a returned handle with `.stop()` for a spawner that keeps running
  * Fireworks are the payoff example, and `demo/worldsmith` already has the parameters
    that look right
* [ ] `Sound` - `lt.sound`, wraps `minetest.sound_play`
  * `lt.sound.play("default_dig_stone", position=Point(...))` at a place,
    `lt.sound.play(name, player=...)` in one player's ears
  * Sound names are game-dependent, so they need the `lt.nodes.names` treatment:
    discoverable by TAB rather than memorised
* [ ] `player.looking_at` - property, wraps `minetest.raycast`
  * Returns the `Node` the player is aiming at, or `None`
  * *"place a block where I am looking"* is a first-class first interactive program and
    currently needs a raycast written in Lua. Highest teaching value in this whole list
  * Second property `player.looking_at_player` is a maybe, not a must
* [ ] `player.hold()` / `player.release()` - `set_physics_override{gravity=0}`,
  `set_properties{collisionbox=...}`, `set_armor_groups{immortal=1}`
  * The one bug in this list that does real damage: `move(destination=...)` to anywhere
    above ground ends in a fall, and in VoxeLibre a camera-height fall is fatal.
    The first full run of the worldsmith demo killed the audience nine times
  * `release()` documents the ordering trap in its first line: **put the player somewhere
    solid before giving physics back**, or it is a fall from wherever the camera stopped
  * `immortal` is the half that matters on its own - a script that darkens the sky has
    summoned mobs whether it meant to or not
* [ ] `move(destination=...)` warns when the destination has nothing under it and the
  player is not held
  * Silently arranging a fatal fall is a poor answer to a correct-looking call

## player_near

The event a *"step on this and something happens"* lesson needs, and the one that cannot
be an entry in the `EVENTS` table in `mod_data/miney/callbacks.lua` like the other ten.

```python
@lt.callbacks.on("player_near", {"pos": Point(10, 20, 30), "radius": 5})
def welcome(event):
    lt.chat.send_to_player(event.player_name, "You found it!")
```

* [ ] Poll positions in the mod, not per server step
  * There is no Luanti registrar for this, so it is a `globalstep` walking the subscribed
    areas. Default around 0.25 s, per-subscription override
* [ ] The area lives in the subscription record, not in `matches()`
  * `matches()` does equality and lists only, and refuses a `Point` on purpose. Distance is
    checked before `matches()` runs, and `player_name` stays an ordinary filter next to it
* [ ] Edge-triggered: fires when a player **enters** the radius, not for every tick spent
  inside it
  * The mod keeps who is currently inside which area, per subscription. Leaving and coming
    back fires again
* [ ] Payload: `player_name`, `pos` (the area, so one handler can serve several), `distance`
* [ ] `radius` is required and has no default
  * A missing radius has no sensible guess, and a wrong one is a handler that fires for the
    whole map
* [ ] Cost is bounded by subscriptions, not by players
  * Ten areas and ten players is a hundred distance checks four times a second, which is
    nothing. Say so in the docstring so nobody is afraid of it
* [ ] Raise `MOD_API` / `REQUIRED_MOD_API` together with this

A `player_leaves_area` twin is deliberately left out until somebody wants it - the state
to fire it is already there, so it stays cheap to add later.

## AI and simulation

Miney's second audience: agents driving many entities, and game logic written in Python
that Luanti has no way to express.

* [ ] Read the world around a point in one call - blocks, entities, players
  * Not "like a client would": the mod can already see all of it, and one Lua chunk
    beats fifty round trips. `Batch reads` above is the mechanism
* [ ] Say what an outer loop can and cannot do, in the docs
  * A reactive handler costs two server steps (~60 ms). A callback whose return value
    the engine reads - `on_punchplayer` returning `true`, `on_player_hpchange` as a
    modifier, `allow_player_inventory_action` - can **never** be answered from Python,
    over any transport. Worth one paragraph so nobody looks for it
* [ ] A named pattern for "policy in Python, tick in Lua"
  * `lt.lua.run` with a `globalstep` already does it. What is missing is the shape, and
    the docs page that says this is how you drive a hundred entities

## Documentation

* [ ] Better first steps guide
* [ ] Python learning lessons that build on each other
* [ ] Education material for beginners, teachers and students
* [ ] Multilanguage

## Infrastructure

* [ ] Github-Actions
  * [x] run tests
  * [x] Tests for pull requests
  * [x] Build and push to pypi for tagged commits
  * [x] Build and push to Luanti ContentDB for tagged commits
