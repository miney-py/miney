# TODO

A list of things i'm planning to do. There will be no fixed timeline.

Feel free to contribute!

## General



## API

* [x] `lt.items` - autocomplete for every name that can be in a hand
  * `lt.tool` covered `registered_tools` and `lt.nodes.names` the nodes; craftitems -
    sticks, coal, ingots - had nothing, and `player.wielding` can answer with all three
  * `NameIterable` is now the one implementation, with `ToolIterable` and `ItemIterable`
    as four-line subclasses that only carry their own docstring and `__repr__`
  * Fixed on the way: every `__getitem__` in that family read `parent.node_types`, which
    exists nowhere in the package, so indexed lookup raised `AttributeError` in all of
    them. Names are sorted now, `len()` of a category counts that category, and the
    dead `parent` argument is gone
* [x] Convenience aliases for `Player.move()`: `teleport()`, `look_at()`, `fly_to()`, `turn()`
  * Thin wrappers around `move()`, not separate implementations
  * Each one documents the equivalent `move()` call, so the alias teaches the general function
  * `fly_to()` carries `duration` and `wait` and nothing else, `turn()` only the two
    angles. Every combination beyond that - flying while turning, an animated turn -
    stays a `move()` call, which is what keeps these four from becoming a second API
  * `turn()` with neither angle raises instead of doing nothing, and the message names
    `look_at()` for whoever wanted a place rather than an angle
* [x] Callbacks
  * [x] Basic API and some callbacks implemented
  * [x] Implement more "register_on_..." functions
  * [x] `player_near` - fire when a player comes within a radius of a position (see below)
* [ ] Asyncio
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
* [ ] Mesecons: Add a python script processor that executes python code.
* Python driven mobs?

## Presentation

Everything here is one or two lines of Luanti Lua today, written by hand through
`lt.lua.run()` with manual `lua.dumps()` quoting. `demo/worldsmith/worldsmith/fx.py` is
the workaround for all of it; the goal is to delete that file.

Each entry is one class, reached through a property, never constructed by the user.
Per-player things hang off `Player`, world-wide things off `Luanti`.

* [x] `Sky` - `player.sky`, wraps `set_sky` / `set_sun` / `set_moon` / `set_stars` /
  `set_clouds` / `override_day_night_ratio`
  * Six properties and a `reset()`. Design in
    `docs/superpowers/specs/2026-07-29-player-sky-design.md`
  * The zombie trap in the old entry here was wrong: sky parameters live on
    `RemotePlayer` and go to that one client, so nothing spawns from them. The warning
    belongs to `lt.time_of_day`, and the docstring says so
* [x] `Particles` - `lt.particles`, wraps `minetest.add_particlespawner`
  * One `spawn()` and a returned handle with `.stop()`. Design in
    `docs/superpowers/specs/2026-07-29-particles-design.md`
  * `add_particle` was left out on purpose: `spawn(amount=1)` says the same thing
  * The mod now ships `textures/miney_spark.png`, so the default works in every game
    instead of needing a texture name nobody can guess, and `forget_session` deletes
    the spawners a session leaves behind
* [x] `Sound` - `lt.sound`, wraps `minetest.sound_play` / `sound_stop` / `sound_fade`
  * One `play()` and a handle with `.stop()` / `.fade_out()`. Design in
    `docs/superpowers/specs/2026-07-29-sound-design.md`
  * The place parameter is `point=`, not `position=`: `lt.particles.spawn(point, ...)`
    already calls it that, and `Point` is the class it takes
  * `player=` is *who hears it*, `follow=` is *where it comes from* - two parameters,
    because one called `player` would have meant either
  * Names went to `lt.assets.sounds` rather than `lt.sound.names`. Sounds are media, the
    scan is the one `textures` already does, and `demo/HANDOFF-hud-assets.md` chose the
    name "assets" for exactly this
  * `lt.assets.upload()` takes `.ogg` now, so a script can bring its own music
  * The mod ships 47 CC0 effects from Kenney's *Digital Audio* as `sounds/miney_*.ogg`,
    so `play()` works in every game instead of needing a name only VoxeLibre knows. The
    15 stereo files in that pack were left out: Luanti positions mono only, so `point=`
    would have been ignored without a word
* [x] `player.looking_at` - property, wraps `minetest.raycast`
  * Returns the `Node` the player is aiming at, or `None`
  * *"place a block where I am looking"* is a first-class first interactive program and
    currently needs a raycast written in Lua. Highest teaching value in this whole list
  * The ray starts at `eye_height`, not at `get_pos()` - from the feet it aims at the
    floor whenever the player looks level. `liquids = true`, because being told
    *"nothing there"* while looking at a lake reads as a bug
  * Reach is `player.look_range`, 10 by default. Luanti's own is 4, which is too short
    for pointing at something across a room
  * Second property `player.looking_at_player` is a maybe, not a must
* [x] `player.hold()` / `player.release()` - `set_physics_override{gravity=0}`,
  `set_armor_groups{immortal=1}`
  * Two methods and a read-only `player.held`. Design in
    `docs/superpowers/specs/2026-07-30-player-hold-design.md`
  * The one bug in this list that does real damage: `move(destination=...)` to anywhere
    above ground ends in a fall, and in VoxeLibre a camera-height fall is fatal.
    The first full run of the worldsmith demo killed the audience nine times
  * `release()` documents the ordering trap in its first line: **put the player somewhere
    solid before giving physics back**, or it is a fall from wherever the camera stopped
  * `immortal` is the half that matters on its own - a script that sets `lt.time_of_day`
    to night has summoned mobs whether it meant to or not. (`player.sky` has not: that
    is one client's rendering and the world stays as bright as it was)
  * `set_properties{collisionbox=...}` was dropped: zeroing it is passing through walls,
    which is `player.noclip`, not the fall. So is `speed=0` - a held player still walks,
    floating, and `player.speed` does not have to lie about what the user set
  * The previous values go into the player's own metadata, the way `invisible` does, so a
    script that dies mid-hold leaves a way back. `gravity` is stored as one number and
    the armor groups whole, because `set_physics_override` merges field by field
    (`l_object.cpp:1900`) while `set_armor_groups` replaces the list (`:385`)
* ~~`move(destination=...)` warns when the destination has nothing under it and the
  player is not held~~ - dropped. `hold()` is the answer to that fall, and a warning on
  every legitimate flight is noise nobody reads

## player_near

The event a *"step on this and something happens"* lesson needs, and the one that cannot
be an entry in the `EVENTS` table in `mod_data/miney/callbacks.lua` like the other ten.

```python
@lt.callbacks.on("player_near", {"pos": Point(10, 20, 30), "radius": 5})
def welcome(event):
    lt.chat.send_to_player(event.player_name, "You found it!")
```

* [x] Poll positions in the mod, not per server step
  * There is no Luanti registrar for this, so it is a `globalstep` walking the subscribed
    areas. Default around 0.25 s, per-subscription override
  * The `EVENTS` entry carries `on = false` rather than no `on` key at all, so the one
    event without a registrar reads as a decision. `register_events()` skips it, and
    `valid_filter()` and `event_names()` treat it like every other event for free
* [x] The area lives in the subscription record, not in `matches()`
  * `matches()` does equality and lists only, and refuses a `Point` on purpose. Distance is
    checked before `matches()` runs, and `player_name` stays an ordinary filter next to it
  * The split happens in Python, in `_area_from()`, *before* the filter validation - so
    `_is_comparable()` never sees the `Point` it would reject
* [x] Edge-triggered: fires when a player **enters** the radius, not for every tick spent
  inside it
  * The mod keeps who is currently inside which area, per subscription. Leaving and coming
    back fires again
  * `inside` is marked whether or not the filter matches. Marking only on a match would
    re-test that player every interval they stand there, which is a level trigger
    wearing an edge trigger's name
  * `register_on_leaveplayer` clears the name from every area. Without it somebody who
    disconnects while inside stays inside forever, and the callback quietly stops working
* [x] Payload: `player_name`, `pos` (the area, so one handler can serve several), `distance`
  * Which is also why this event sends one message *per subscription* rather than one per
    client the way `broadcast()` does: two areas have two payloads and cannot share one
* [x] `radius` is required and has no default
  * A missing radius has no sensible guess, and a wrong one is a handler that fires for the
    whole map
* [x] Cost is bounded by subscriptions, not by players
  * Ten areas and ten players is a hundred distance checks four times a second, which is
    nothing. Say so in the docstring so nobody is afraid of it
* [x] Raise `MOD_API` / `REQUIRED_MOD_API` together with this - both at 13 now

A `player_leaves_area` twin is deliberately left out until somebody wants it - the state
to fire it is already there, so it stays cheap to add later.

## Feature parity with the Luanti API

What a walk through `luanti-src/doc/lua_api.md` turned up that Miney has no answer for.
Ordered by teaching value, not by how much of the API each one covers. Entries already
listed above - `player.looking_at`, `player.hold()`, batch reads, mobs - are named here
only where something new hangs off them.

**The wall, first - and it is four walls, not one.** The *Registration functions* section
of `lua_api.md` opens with *"Call these functions only at load time!"*, which reads like
one flat rule. The engine sources say otherwise, and the four cases are as different as
they get. Anything Miney does here is off the documented contract either way, so the
notes below are why each case behaves as it does, not permission to rely on it.

**Works, because it is a plain Lua table.** `register_chatcommand` (the mod already calls
it at runtime), every `register_on_*` (`make_registration()` in
`builtin/game/register.lua`, table read per event), `register_privilege`
(`builtin/game/privileges.lua`) and - the surprise - `register_entity`:
`register.lua:118` writes `core.registered_entities[name]` and `s_entity.cpp` reads that
table **at spawn time**.

**`register_craft` works**, marginally slower. A late recipe lands in the
`CRAFT_HASH_TYPE_UNHASHED` bucket in `craftdef.cpp`, and the lookup loop runs
`type <= craft_hash_type_max`, which *is* `CRAFT_HASH_TYPE_UNHASHED` (`craftdef.h`). So
it is found, it just stays a linear scan instead of a hash hit. `initHashes()` ran back
at `server.cpp:562` and is not run again.

**`register_abm` and `register_lbm` do nothing at all, and say nothing.** `readABMs()` /
`readLBMs()` are called exactly once, from `initializeEnvironment` at `server.cpp:585`,
and `ServerEnvironment::addActiveBlockModifier` has exactly one caller in the tree. The
Lua table grows, the C++ side never looks at it again. No error, no effect - the worst
shape a failure can have.

**`register_biome`, `register_ore`, `register_decoration` and `register_schematic` abort
the server process.** They ask `EmergeManager` for a writable manager, and that is

```cpp
FATAL_ERROR_IF(!m_mapgens.empty(),
    "Writable managers can only be returned before mapgen init");
```

`initMapgens` runs at `server.cpp:581`, before any mod gets a single runtime step, so the
condition is always true. `FATAL_ERROR` aborts. One `lt.lua.run()` and the world is gone.

**`register_node`, `register_craftitem` and `register_tool` run clean and leave three
kinds of wreckage.** There is no load-time guard - `l_item.cpp` calls
`idef->registerItem` and `ndef->set`, and `NodeDefManager::set` cheerfully allocates a
fresh content id. But:

1. `SendItemDef` and `SendNodeDef` have one call site, in the client-init handshake in
   `serverpackethandler.cpp`. A player who is already connected never learns the node
   exists and sees an unknown node.
2. `server.cpp` already ran `setNodeRegistrationStatus(true)`, `runNodeResolveCallbacks()`
   and `resolveCrossrefs()`. A late definition's `_name` cross-references never resolve.
3. **The map stores the name and nothing stores the definition.** After a restart nobody
   re-registers it, so every node placed that way is permanently unknown. That is damage
   to the world file, not a missing feature.

So two things come *off* the impossible list: crafting recipes, which work at runtime and
only need somewhere to be written down (see *Definitions that survive a restart* below,
and `get_craft_result` / `get_all_craft_recipes` become worth having next to them), and
entities, which do not need a fixed puppet shipped in the mod after all (see *Entities*).

And the rest of the wall turns out to be a delay rather than a refusal - the next section
is what that costs.

And one goes into the docs:

* [ ] Say what happens per registrar, next to the paragraph about callbacks whose return
  value the engine reads
  * Same kind of fact, same place. Worth naming the mapgen four explicitly: *"this one
    kills the server"* is not a sentence anyone should have to discover twice

### Definitions that survive a restart

The way around the wall, for everything the wall actually blocks. Python does not call
the registrar; it **writes down what should be registered**, the mod replays that list at
load time, and Miney says out loud that a restart is needed before the new thing exists.
What comes back after the restart is not a workaround - it is the real registration, at
the only moment the engine accepts one, so the definition is complete and permanent.

Three pieces already exist and are the reason this is worth doing at all:

* `core.get_mod_storage()` - *"must be called during mod load time"* (`lua_api.md`), and
  `init.lua` already calls it. So the store is `lt.storage` mechanics, no new file
  handling, no path logic
* The replay runs inside `init.lua`, which **is** load time. That removes all four walls
  at once: clients get the definitions in the join handshake, `resolveCrossrefs()` runs
  afterwards, the mapgen managers are still writable, `readABMs()` has not run yet
* **Textures already survive.** `keep = true` in `assets.lua` writes into the one
  mod-writable directory that outlives a restart, and the mod re-announces those files
  when it loads. A self-defined node would therefore also have a look - which is the
  difference between a feature and a demo

* [ ] `lt.nodes.define(name, texture=..., groups=..., drop=...)` - the case the whole idea
  is for
  * `register.lua` enforces a `miney:` prefix and `[%w_]` only, so `define("mystone")`
    becomes `miney:mystone` and cannot collide with anything a game ships. Validation for
    free, namespacing for free
  * Callbacks in a nodedef (`on_punch`, `can_dig`, `after_place_node`) are Lua closures and
    cannot be written down. They stay out, and it costs almost nothing: `lt.callbacks` on
    `dignode` and `placenode` already gives Python the reaction
  * *"You just made a new kind of block, and it is still there tomorrow"* is the best
    sentence in this file. It is also not day-one material - see the restart cost below
* [ ] `lt.crafting.add(...)` is the one with no restart at all
  * `register_craft` works at runtime, so the store only has to make it *permanent*. Applied
    immediately, replayed on the next start. Same mechanism, no waiting, and it means the
    feature has a beginner-facing half
* [ ] Ore, decoration, biome and schematic definitions
  * Declaration-only is not a compromise here, it is the **only** possible route: calling
    these at runtime aborts the server. Written down and replayed, they are legal
  * Docstring has to say that mapgen only touches **newly generated** chunks. *"Make
    diamonds spawn everywhere"* and then standing in an already-generated world is the
    obvious first disappointment
* [ ] `lt.pending_restart` and, where possible, `lt.restart()`
  * A definition that is stored but not yet live must be visible, not implied. A list is
    the honest shape, and the returned object's `__repr__` says it too
  * `manage.py` has `stop_pid`, `is_pid_alive` and `server_pid`, so restarting from Python
    is possible - **but only when `miney start` started the server.** Launched from
    Luanti's main menu there is no state file, and then all Miney can do is say the
    sentence
  * A restart disconnects the player and empties both channel files, so the live session
    has to resynchronise afterwards. That is the real price, and it is why this belongs in
    a setup script run once rather than in the middle of a lesson
* [ ] Every replayed entry in its own `pcall`
  * **The one thing that must not be got wrong.** A bad entry escaping `init.lua` means
    the world no longer starts, and there is no Python session left to delete it from.
    Skip it, log it, keep loading
* [ ] `uv run miney reset-definitions <world>`
  * `pcall` saves the start, not the content. A definition that loads fine and is simply
    wrong - a texture name that does not exist, so every client sees the unknown-texture
    checkerboard - needs a way out that does not require a working session
* [ ] Raise `MOD_API` / `REQUIRED_MOD_API` with this
* [ ] ABM and LBM definitions - only if somebody asks
  * They would work through the same store, but the *action* is a Lua function, and a
    per-node callback answered from Python is two server steps per node. So the value is
    a Lua source string in the store, which is a different feature wearing this one's
    clothes. Left out for now

### Reading the world

Searching is in - `find` and `find_in` below. What is left is everything else a block
can be asked about.

* [x] `lt.nodes.find(name, near=Point(...), radius=10)` and
  `lt.nodes.find_in(start, end, name)` - `find_node_near`, `find_nodes_in_area`,
  `find_nodes_in_area_under_air`
  * *"Where is the nearest water"* is a `for` loop over the result, which is first-week
    Python against a 3D world
  * `find_nodes_in_area_under_air` is what *"put a torch on every stone I can see"*
    needs, and nobody would write that filter themselves - it is `under_air=True` on
    `find_in`, not a third method
  * Both answer with `Node`, not `Point`, and the name is read back per position rather
    than taken from what was asked for: `"group:tree"` matches several names and the
    answer should say which one is standing there. That also made `grouped` unnecessary -
    the dict per name would have been a second return shape for the same question
  * `search_center` is always `true`, unlike Luanti's own default. Standing on dirt and
    being told the nearest dirt is a block away reads as a bug, and no radius can express
    the other behaviour anyway, so it is not a parameter
  * A name this server does not have raises. A search that silently finds nothing looks
    exactly like a world that has none of it, which is the wrong lesson for a typo.
    `group:` is let through unchecked - Luanti has no list of the groups a game defines
* [x] `node.meta` - `core.get_meta`, `NodeMetaRef`
  * Sign text, furnace state, whatever a game stored there. `node.inventory` is already
    the other half of the same object, so this is one property on a class that exists
  * `_MetaStore` took the whole thing: it already takes the Lua expression that finds
    the ref as an argument, so this is that base with `prefix=""` and nothing else
  * No prefix, unlike `player.storage` - the keys the *game* wrote are the entire point,
    and a prefix would hide every one of them. The price is that `clear()` wipes the
    block's own data, and the docstring says so in a warning
* [x] `player.looking_at` - see the Presentation list above. Still the highest-value
  single property in this file
* [x] `lt.nodes.light_at(point)` - `get_node_light` / `get_natural_light` /
  `get_artificial_light`
  * *"Is it dark enough for mobs here"*, and the answer is a number a beginner can print
  * Only `get_node_light` went in. Splitting the answer into sunlight and torchlight is
    a second question nobody has asked, and one number you can print is the feature -
    so the other two are a note here rather than a parameter
  * `None` for an unloaded area, which is a normal answer read with `if`. The docstring
    carries the trap from `lua_api.md:6928`: the light is measured *inside* the block,
    so a solid block always answers 0 and you measure the air above the ground
* [ ] `lt.nodes.biome_at(point)` - `get_biome_data`, `get_biome_name`, `get_heat`,
  `get_humidity`
  * Low priority. Real, but nothing a lesson has asked for

### Writing the world like a player does

* [x] `lt.nodes.place()` and `lt.nodes.dig()` - `core.place_node`, `core.dig_node`
  * **This is a bug, not a feature request.** `nodes.set()` goes through `set_node`,
    which skips `on_place` - so a door placed by Miney has no top half, a torch faces
    nowhere and a chest has no inventory. The call looks correct and the result is wrong
  * `place_node` runs the game's own placement logic and takes a `placer`, so it also
    fixes orientation for free
  * Two methods, not a flag on `set()`. Digging has no `set()` to hang off in the first
    place, and one of the two would have ended up somewhere else than the other
  * Both return **how many the server really did**, and that is the whole reason they
    wait for an answer where `set()` does not: `place_node` and `dig_node` answer `false`
    for a protected area, and dropping that on the floor would be the same silent
    failure this entry is about. `set()` stays the fast path that sends and forgets
  * Both `load_area` first. `l_env.cpp` returns `false` outright where the map is not in
    memory - *"Don't attempt to load non-loaded area as of now"* - so without it,
    building away from a player is a hundred refusals and no blocks
  * `player=` is a name or a `Player`, and it is looked up **in Lua before anything is
    placed**, with an `error()` if they are not there. Passing a name that is offline had
    to mean something other than "nobody at all"
  * `punch_node` was left out. It is a third verb for a thing nobody has asked to do from
    Python, and `dig` covers what a lesson wants
  * `set()` and `fill()` now say in their own documentation what they leave out, and
    `docs/api/nodes.rst` is three ways to build instead of two - the old prose claimed
    `set()` gave a chest its inventory, which is exactly the bug
* [ ] Make `Node.param2` mean something - `rotate_node`, `dir_to_facedir`,
  `facedir_to_dir`, `dir_to_wallmounted`, `yaw_to_dir`
  * Today it is a raw int nobody can read. A `node.facing` that takes and returns a
    `Vector` would turn the single worst trap in node placement into a direction
* [x] `lt.nodes.grow_tree(point)` - `core.spawn_tree`
  * A tree from one call. Cheap to add, immediately visible, and the `treedef` table can
    stay hidden behind keyword arguments
  * Not as cheap as this entry claimed: `spawn_tree` needs a whole L-system definition,
    and the two fields that really differ - trunk and leaves - differ per *game*. The
    mod guesses them (`default:*`, then `mcl_core:*`) and errors naming `trunk=` and
    `leaves=` when neither is there, so `grow_tree(point)` stays one line everywhere
  * `height` builds the axiom: `("F"):rep(height - 3) .. "AFFBF"`, which at the default
    8 reproduces the apple tree from `lua_api.md:5975` character for character
* [ ] Schematics - `create_schematic`, `place_schematic`, `read_schematic`
  * Copy a building and stamp it somewhere else, with rotation. High wow, moderate API,
    and it is the one thing in this section a lesson could be built around
* [ ] `swap_node` as an option somewhere
  * Keeps metadata and fires no callbacks. Different from `set_node` in a way that only
    matters once somebody hits it

### The player

`Player` covers position, look, hp, breath, the physics overrides and privileges. The
`ObjectRef` methods worth having on top, roughly in order:

* [x] `player.wielding` - `get_wielded_item`
  * *"What am I holding"*, and together with `looking_at` it is the first interactive
    program a beginner writes
  * Read-only, and `set_wielded_item` / `get_wield_index` stay out. Writing there
    **replaces** the stack, so `player.wielding = "default:pick_mese"` would delete 64
    blocks of dirt to put one pick in their place. `player.inventory.add()` is the way
    to give somebody something
* [x] `player.keys` - `get_player_control`
  * Which keys are held, as a dict of bools. `if player.keys["jump"]:` is a reactive
    program without touching callbacks or decorators
  * Only the booleans. `LMB`/`RMB` are documented duplicates of `dig`/`place`, and
    `movement_x`/`movement_y` are floats that do not exist before 5.10 - a dict that
    promises True or False keeps that promise on every server Miney supports
* [x] `player.velocity` and `player.push(vector)` - `get_velocity`, `add_velocity`
  * Launch a player. One line, unmistakably visible, and `Vector` already exists to
    express it
  * `velocity` is read-only: players do not support `set_velocity` at all (`lua_api.md`,
    *"players also do not support set_velocity"*), so `push()` is the only way in
* [x] `player.size` - `set_properties{visual_size=...}`
  * Giant or tiny player from one float. Pure spectacle, almost no code
  * Only the picture. The collision box is separate, so a giant still fits through a
    normal door - said in the docstring, because it looks like a bug otherwise
* [x] `player.storage` - `get_meta`, `PlayerMetaRef`
  * The per-player twin of `lt.storage`, which is world-wide. `Storage` and
    `PlayerStorage` now share a `_MetaStore` base: same `MutableMapping`, different Lua
    expression, different prefix
  * Called `storage` and not `meta` on purpose. Keys are filed under `miney:data:`, so a
    game's own notes about the player - and the records `hold()` and `invisible` leave -
    stay out of sight and out of reach of `clear()`. That makes it a store of ours next
    to `lt.storage`, not the player's metadata, and the name should say which
  * Reads and writes wait for the server, unlike `lt.storage`: the player can leave, and
    a write nobody hears fail is a script that believes it saved something
* [x] `player.respawn()` - `respawn()`
  * In 5.9 already, checked against the tag - no version guard needed
* [x] `player.armor_groups` - `set_armor_groups`
  * `immortal = 1` is the half that matters and is already called for by
    `player.hold()`. A property is the honest place for it
  * Assigning replaces the whole table, the way Luanti does it. Documented as a warning
    with the read-change-assign pattern next to it

### More callbacks

Eleven events exist. Registrable and missing: `on_rightclickplayer`, `on_newplayer`,
`on_craft`, `on_item_eat`, `on_item_pickup`, `on_cheat`, `on_priv_grant`,
`on_priv_revoke`, `on_protection_violation`, `on_generated`, `on_mapblocks_changed`,
`on_liquid_transformed`, `on_modchannel_message`.

* [ ] `on_rightclickplayer` and `on_craft` first
  * Both are things a lesson does. The rest is infrastructure with no story attached
* [ ] The others are one line each in the `EVENTS` table
  * Add them when something wants them, not as a sweep. `on_generated` and
    `on_mapblocks_changed` fire per mapblock and would flood the channel - if they go in
    at all they need a filter on the mod side first

### Formspecs

The one large subsystem Miney has nothing for: `show_formspec`,
`on_player_receive_fields`, `close_formspec`, `formspec_escape`. Real dialogs with
buttons, fields and dropdowns, driven from Python, with the answer arriving as an event -
which is exactly the shape the channel already has.

* [ ] Decide whether this belongs in Miney at all
  * `lua_api.md` documents around sixty element types. A faithful wrapper is bigger than
    `Hud` and `Sky` together, and `Hud` already covers what a classroom asks for
  * A small honest subset - a dialog with a title, some labels, some fields, some buttons,
    and one handler receiving a dict - is maybe a tenth of that and would carry its weight
  * Nothing is decided here. It is on the list so the question is on the record

### Entities

The mechanism behind *"Python driven mobs"* in the General list.

* [ ] Register the prototype from Python - `core.register_entity` works at runtime
  * `register.lua` writes it into `core.registered_entities` and `s_entity.cpp` reads that
    table when `add_entity` spawns, so nothing has to be decided at load time. The
    `visual`, `textures` and `mesh` reach the client through `LuaEntitySAO`'s property
    update, which is dynamic - unlike node definitions, entities do not need the client to
    have been told at join
  * So `lt.entities.spawn(point, texture=..., visual=...)` is a Python-only feature and the
    mod does not need to ship a generic `miney:puppet` after all
  * The tick still belongs in Lua. An `on_step` answered from Python costs two server
    steps per step, which is not a mob, it is a slideshow. The prototype's `on_step` stays
    a Lua closure written once through `lt.lua.run()`; Python sets the *policy* - where to
    go, what to do - and reads state back
* [x] `lt.entities.near(point, radius)` - `get_objects_inside_radius`
  * Miney currently cannot see a single mob, dropped item or entity in the world.
    Needed by anything reactive, and it is one call
  * It went to a namespace of its own rather than `lt.objects_near()` on the façade:
    `spawn()`, `find_path()` and `clear()` all belong next to it, and a method on
    `Luanti` would have been the one that ended up somewhere else than its siblings
  * `players=False` by default. A player is always within any radius of themselves,
    and meeting yourself in the answer to *"what is near me"* is a surprise in the
    first loop somebody writes
  * `get_objects_inside_radius`, not the `objects_inside_radius` iterator - that one is
    newer than 5.9, and what it guards against cannot happen to a call that only reads
  * Left out: the real name of a dropped item. Everything on the ground is
    `__builtin:item` and digging out what it *is* is game-specific
* [ ] `get_objects_in_area` - the box-shaped twin of `near()`
  * Same call shape, `find_in` to `near`'s `find`. Nobody has needed it yet
* [ ] `core.find_path` - free A* from the engine, no Python pathfinding needed
  * Makes *"walk over to the player"* a single call instead of a lesson in graph search
* [ ] `clear_objects` - clean up after a script that spawned too much

### Presentation, one level down

`Sky`, `Sound`, `Particles` and `Hud` are done. Still hand-written Lua, and all of it
per-client like `Sky` is:

* [ ] `player.lighting` - `set_lighting`: `saturation`, `shadows`, `exposure`, bloom,
  volumetric light
  * Sits directly next to `player.sky`, same shape, same one-client semantics, same
    "the game may repaint it" caveat
  * Every field is ignored on a client with the matching effect switched off. The
    docstring has to say so, or it reads as a Miney bug
* [ ] `player.fov` - `set_fov(fov, is_multiplier, transition_time)`
  * A zoom, with a built-in transition. One number, large effect
* [ ] `player.camera` - `set_camera{mode=...}`, first or third person
  * **Clients only support it from 5.12.0.** Miney supports 5.9, so this one needs a
    version check and a clear message, not a silent no-op
* [ ] `set_attach` / `set_detach` - ride an entity, or another player
  * Depends on the entity work above to be worth anything
* [ ] The small ones: `set_texture_mod` (tint a skin), `set_nametag_attributes` (public -
  `player.invisible` already sets it internally), `set_local_animation`, `set_eye_offset`,
  `set_observers` (who the player is sent to), `set_minimap_modes`,
  `set_formspec_prepend`

### Server administration

`kick_player`, `ban_player`, `unban_player_or_ip`, `get_ban_list`, `request_shutdown`,
`get_server_status`, `get_server_uptime`, `get_server_max_lag`, `set_player_password`,
`player_exists`, `remove_player`, `get_player_information` (ping, client version),
`get_player_window_information`, `is_protected`, `is_area_protected`.

* [ ] Probably don't
  * None of it teaches Python, and Miney runs beside a single-player server on the same
    machine, where most of it is meaningless. If it ever goes in it is an `lt.server`
    namespace kept out of the introductory docs
  * `get_player_information` is the one with a use - ping and protocol version explain a
    laggy demo - and it does not need the rest of the list to come with it

### Left out on purpose

* `ValueNoise` / `PerlinNoise` - Python's own noise libraries are better and the learner
  is in Python already
* `AreaStore` - a spatial index for a problem nobody has
* `VoxelManip` as a public API - `nodes.fill()` already uses it internally, which is the
  right place for it
* `get_node_drops` - real, but it answers a question about the game's content rather than
  doing anything in the world. (`get_craft_result` and `get_all_craft_recipes` moved up to
  the crafting entry, where they have something to be next to)
* `emerge_area`, `forceload_block` - the mod calls `load_area` where it needs to. Exposing
  the rest invites a script that pins half the map into memory

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
