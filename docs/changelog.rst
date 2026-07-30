=========
Changelog
=========

All notable changes to this project will be documented in this file.
The format is based on `Keep a Changelog <https://keepachangelog.com/en/1.0.0/>`_ (added, changed, deprecated, fixed,
removed and security sections),
and this project adheres to `Semantic Versioning <https://semver.org/spec/v2.0.0.html>`_.

Unreleased
----------

**Added**

- ``node.meta`` - the little table of text Luanti keeps on a block, used like a
  dictionary. A sign's words, the ``infotext`` you see when you point at something,
  whatever the game stored there::

      sign = lt.nodes.get(Point(0, 10, 0))
      sign.meta["text"] = "This way"

- **A world you started yourself in Luanti now works.** ``miney.Luanti()`` finds the
  server on your computer whoever started it - a world from ``uv run miney start``, or
  a singleplayer world you opened from the Luanti menu, which Miney could not reach at
  all before. No account, no password, no port, and nothing joins your world: Miney and
  the mod pass messages through two files in Luanti's own data directory. Running
  several worlds at once is the one case that still needs a word from you, and the error
  message lists them: ``miney.Luanti(world="myworld")``.
- **Loops are hundreds of times faster, and nothing about them changes.** A command that
  has no answer to give - placing a node, sending a chat message, setting a position -
  no longer waits for the server before your next line runs. The server picks up
  everything that has arrived in one go, so a whole loop costs one server step instead
  of one step per iteration. Measured on a real server, a plain ``for`` loop placing 400
  nodes one at a time: **12.2 s before, 0.06 s now**; 2500 nodes take 0.36 s.

  .. code-block:: python

      for x in range(50):
          for z in range(50):
              lt.nodes.set(Node(x, 20, z, lt.nodes.names.default.wood))

  Anything that reads waits for the world to catch up first, so ``lt.nodes.get()`` after
  a loop sees the blocks. Nothing is lost when a script simply ends, either. An error
  from a command Miney had already sent on is raised at the next line that waits, and
  the message names the line it really came from. :meth:`lt.lua.flush()
  <miney.Lua.flush>` waits on demand, and :meth:`lt.lua.run() <miney.Lua.run>` takes
  ``wait=False`` for Lua of your own.
- ``uv run miney start`` asks the server for a step every 0.03 seconds instead of the
  default 0.09 - what a game hosted from the Luanti menu runs at anyway. That is the
  whole of the delay on a command that does wait for an answer, so it cuts it by two
  thirds: 90 ms to 30, measured on a real server.
- ``player.hud`` - the screen. A chat message scrolls away; this stays.
  :meth:`player.hud.text() <miney.Hud.text>` puts a line on a player's screen and gives
  back a handle to change it later, ``score.text = "Score: 7"``. Waypoints, images,
  statbars, inventory and compass elements go the same way, all of them one line around
  :meth:`~miney.Hud.add`. ``position`` takes one of nine names instead of numbers, and
  Luanti's field names are translated - ``color="#ffcc00"`` rather than
  ``number = 0xffcc00``. What Luanti draws by itself is here too:
  ``player.hud.healthbar = False``, ``player.hud.hotbar_slots = 4``.
- ``player.sky`` - the sky one player sees. ``player.sky.color = "#101040"`` replaces
  Luanti's painted sky with a flat colour, and :attr:`player.sky.brightness
  <miney.Sky.brightness>` turns noon into night without touching the clock. ``clouds``,
  ``sun``, ``moon`` and ``stars`` switch on and off, and :meth:`player.sky.reset()
  <miney.Sky.reset>` puts everything back - a script that darkens a sky and ends leaves
  the player in it otherwise. All of it is what that one player sees: the world stays
  bright, and no mob spawns because of it.

  A game that paints its own sky is handled: VoxeLibre repaints every player about once
  a second, which used to wipe a colour out before the next line of a script ran. Miney's
  mod is now the last link in that game's own chain of sky filters and lays what a script
  set over what the game decided - for that one player, leaving everybody else's weather
  and every part of the sky nobody claimed alone.
- :meth:`player.hold() <miney.Player.hold>` and :meth:`player.release()
  <miney.Player.release>` - **a player you move is no longer killed by the trip.**
  ``player.move(destination=...)`` to a point above ground ends in a fall, and in games
  like VoxeLibre a fall from camera height is fatal, so a correct-looking line came back
  with a corpse. Held, the player floats where they are and takes no damage at all - not
  from the fall, not from drowning, not from the mobs a script summoned by setting
  :attr:`lt.time_of_day <miney.Luanti.time_of_day>` to night.

  .. code-block:: python

      player.hold()
      player.move(destination=Point(200, 80, 200), smooth=True, duration=5, wait=True)

      player.move(destination=Point(200, 12, 200))    # somewhere solid, first
      player.release()

  ``release()`` gives back what the player really had, not Luanti's defaults over the top:
  a script that set ``player.gravity = 0.5`` gets ``0.5`` back. That is written into the
  player's own data, so a script that stops halfway still leaves a way out. Put the player
  somewhere solid before you release them - otherwise it is a fall from wherever they were
  floating. :attr:`player.held <miney.Player.held>` says whether a hold is on.
- :attr:`player.looking_at <miney.Player.looking_at>` and :attr:`player.wielding
  <miney.Player.wielding>` - **the game can answer questions now, not only obey.** What
  block is somebody pointing at, and what are they holding? Both were a raycast written
  in Lua by hand; both are one word now, and together they are a whole first interactive
  program.

  .. code-block:: python

      target = player.looking_at
      if target and player.wielding == lt.nodes.names.default.torch:
          lt.nodes.set(Node(target.x, target.y + 1, target.z,
                            lt.nodes.names.default.torch))

  ``looking_at`` gives back a :class:`~miney.node.Node`, so it says where as well as
  what, and it goes straight into anything that takes a position. Open sky is ``None``.
  The line runs ten blocks by default - ``player.look_range = 40`` makes it longer.
- :attr:`lt.items <miney.Luanti.items>` - every name that can be in a hand, found with
  TAB. ``lt.items.default.stick`` is ``'default:stick'``. Blocks had
  :attr:`lt.nodes.names <miney.Nodes.names>` and tools had :attr:`lt.tool
  <miney.Luanti.tool>`, but sticks, coal and apples had nothing at all - and
  ``player.wielding`` can answer with any of the three, so this is the one list to
  compare it against.
- :attr:`player.keys <miney.Player.keys>` - which keys somebody is holding down, as a
  dictionary of ``True`` and ``False``. A program that reacts to the game with nothing
  but a ``while`` and an ``if``::

      while True:
          if player.keys["jump"]:
              lt.chat.send_to_all(f"{player.name} jumped!")
          time.sleep(0.5)
- :attr:`player.velocity <miney.Player.velocity>` and :meth:`player.push()
  <miney.Player.push>` - how fast somebody is moving, and a shove in any direction.
  ``player.push(Vector(0, 20, 0))`` throws them into the air;
  ``player.push(player.look_dir * 15)`` sends them wherever they are looking.
- :attr:`player.storage <miney.Player.storage>` - :attr:`lt.storage
  <miney.Luanti.storage>` for one person. A dictionary that stays with that player after
  they log out and after the server restarts, so a script can remember where somebody set
  their home or how far they got::

      visits = int(player.storage.get("visits", "0")) + 1
      player.storage["visits"] = str(visits)
      lt.chat.send_to_player(player.name, f"Welcome back! Visit number {visits}.")

  Your keys are the only ones you see and the only ones ``clear()`` removes - the game
  keeps its own notes about a player in the same place, and nothing you write here can
  disturb them.
- Three more small ones on a player: :attr:`size <miney.Player.size>` makes them a giant
  or tiny from one number (``player.size = 3``, and only the picture changes - they still
  take up one player's worth of room), :meth:`respawn() <miney.Player.respawn>` sends them
  back to where they would appear after dying, without hurting them, and
  :attr:`armor_groups <miney.Player.armor_groups>` says what can hurt them and by how
  much.
- ``lt.particles`` - sparks, smoke and fireworks.
  :meth:`lt.particles.spawn() <miney.Particles.spawn>` throws particles into the world
  from one line, ``lt.particles.spawn(Point(10, 20, 30), color="#ffcc00")``, and gives
  back a handle to stop it with. ``speed``, ``spread`` and ``gravity`` say how they fly,
  ``time`` how long they keep coming and ``life`` how long each one lasts. The image
  they are made of ships with Miney, so the same line looks the same in every game -
  and ``time=0`` runs until :meth:`~miney.ParticleSpawner.stop` says otherwise, or
  until your session ends.
- ``lt.sound`` - a click, a chime, or music that plays until you stop it.
  :meth:`lt.sound.play() <miney.Sound.play>` is one line,
  ``lt.sound.play("miney_power_up_1")``, and gives back a handle with
  :meth:`~miney.PlayingSound.stop` and :meth:`~miney.PlayingSound.fade_out`. ``point=``
  puts the sound in the world so it fades with distance, ``player=`` decides who hears
  it and ``follow=`` makes it travel with somebody. ``loop=True`` turns it into a
  soundtrack - one that keeps playing until it is stopped, or until your session ends.

  Miney's mod brings 47 sound effects along, so that line works in every game instead of
  needing a name one of them happens to know: lasers, zaps, power-ups, beeps and chimes,
  all called ``miney_`` something and all listed in ``lt.assets.sounds.miney``. They are
  **Digital Audio** by `Kenney Vleugels <https://kenney.nl/assets/digital-audio>`_,
  released under `CC0 <http://creativecommons.org/publicdomain/zero/1.0/>`_ - thank you,
  Kenney.
- ``lt.assets`` - pictures and sounds. :attr:`lt.assets.textures
  <miney.Assets.textures>` and :attr:`lt.assets.sounds <miney.Assets.sounds>` make
  everything the server's mods carry findable with TAB, the way ``lt.nodes.names`` does
  for blocks: ``lt.assets.textures.default.dirt`` is ``'default_dirt.png'``,
  ``lt.assets.sounds.default.dig_stone`` is ``'default_dig_stone'``.
  :meth:`lt.assets.upload() <miney.Assets.upload>` sends one of your own the other way -
  a file, raw bytes, a Pillow image, a matplotlib figure, or an Ogg sound - and gives
  back a name usable anywhere a texture or sound name goes. It waits until the file has
  really arrived on the client, so the next line can use it. ``player=`` sends it to one
  player and forgets it again, ``keep=True`` keeps it across server restarts. Neither
  Pillow nor matplotlib is needed to install Miney; they are recognised by the methods
  they carry.
- :meth:`~miney.Lua.run` no longer has a length limit worth thinking about. The old
  route carried less than 640 KB per request and the server dropped anything larger
  without a word, so long code was refused outright. 8 MB now crosses in a single server
  step, indistinguishable from a kilobyte. Code above 16 MB is still refused, which no
  script written by a person will ever reach.
- :class:`~miney.Point` can be compared and used as a key. ``Point(1, 2, 3) ==
  Point(1, 2, 3)`` is ``True``, and a point now goes into a ``set`` or a ``dict`` like
  any other value. Note the trap: ``point += other`` changes the point in place, and a
  point that changed while it sat in a set is not found there anymore - build a new one
  with ``point + other``.
- ``uv run miney init`` says so when the ``.miney`` directory it just created sits in a
  folder synced by Nextcloud, ownCloud, Dropbox or OneDrive. The sync client copies the
  world databases while the server writes them, which kills the server thread with
  *"Couldn't save env meta"*.
- **Miney can find blocks now, not only write them.** :meth:`lt.nodes.find()
  <miney.Nodes.find>` gives you the closest block of a kind around a point, and
  :meth:`lt.nodes.find_in() <miney.Nodes.find_in>` every one of them inside a box. Both
  answer with :class:`~miney.node.Node` objects, so what comes back is a position you can
  use straight away, and both take a whole kind of block at once: ``"group:tree"``,
  ``"group:water"``.

  .. code-block:: python

      water = lt.nodes.find("group:water", near=player.position, radius=20)
      if water:
          lt.chat.send_to_all(f"Water at {water.x}, {water.y}, {water.z}")

  ``find_in(..., under_air=True)`` keeps only the blocks with air above them, which is
  the surface of the terrain — what *"put a torch on every stone I can see"* needs.
- :meth:`lt.nodes.place() <miney.Nodes.place>` and :meth:`lt.nodes.dig()
  <miney.Nodes.dig>` do it the way a player does. ``lt.nodes.set()`` writes the block and
  nothing else, so a chest placed with it has no inventory, a door has no top half and a
  torch faces nowhere — the call looks right and the result is wrong. ``place`` runs the
  game's own placement code instead, and ``dig`` runs the digging code, so a block breaks
  into what it drops rather than simply vanishing. Both take a ``player=``, who then
  decides which way anything rotatable faces and who gets what falls out. ``set`` and
  ``fill`` stay the fast way to build walls, floors and terrain, and now say in their
  documentation what they leave out.
- Short names for the four things :meth:`~miney.Player.move` is usually asked for:
  ``player.teleport(point)``, ``player.look_at(point)``, ``player.fly_to(point,
  duration=3)`` and ``player.turn(yaw=...)``. Each one is a single call to ``move()`` and
  says so, so nothing new happens — there is just something to find when you look for
  "teleport".

**Changed**

- **The Lua mod on the server has to be updated** for the changes above. Miney checks
  while it connects and says so.
- **One command takes longer than it did in v0.7.0**, and that is the price of the line
  above. Logging in as a player let the server answer the moment the request arrived;
  reaching it through its files means waiting for the server's next step, because that
  is when a mod is allowed to run at all. Measured on the same server: 1.6 ms before,
  30 ms now. Loops are not affected - see above, they got much faster - so this is only
  noticeable when a script waits for one answer after another.
- **Luanti 5.9 or newer is required**, up from 5.7. Both of those are years old by now,
  and 5.9 is where the engine learned to accept a media file's contents directly rather
  than a path on the server's own disk - which is what will let a script hand a player
  an image it made in Python. ``uv run miney start`` installs a current Luanti by
  itself, so this only matters if you point Miney at a server somebody else runs.

**Removed**

- **A Luanti on another computer is out of reach.** Miney used to carry a Luanti client
  of its own - the network protocol, the login, the packets - so that it could reach a
  server anywhere and drive it through a player account. That is gone. Everything now
  goes through the two files, which means the server has to be one this machine can see
  on disk.

  It bought 30 ms per command and cost an account, a password, a port, a player standing
  in the world, a 640 KB ceiling per request and about 1800 lines of hand-written UDP and
  SRP code. What a script waits for is answers, not commands, and 30 ms is not what makes
  a script slow - the number of answers it asks for is, and that is what the loop work
  above fixes. Reaching somebody else's server is worth doing properly some day; it is
  not worth a second transport in the meantime.

  ``miney.Luanti()`` is unchanged. ``server``, ``playername``, ``password`` and
  ``invisible`` are gone from it, and a script that passed them raises ``TypeError``
  instead of quietly connecting to the wrong thing. ``lt.luanti``, ``lt.server``,
  ``lt.playername`` and ``miney.LuantiClient`` are gone with them.
- ``miney.LuantiPermissionError``, ``miney.LuantiTimeoutError``,
  ``miney.AuthenticationError`` and ``miney.SessionReconnected`` are gone. Nothing could
  raise them once the login went. ``miney.LuantiConnectionError`` stays and still means
  what it did: Miney cannot reach the server, or the mod on it is too old.
- **The** ``miney`` **privilege is gone**, and so is ``/miney form``, the in-game Lua
  console. The privilege guarded a network client, and there is no longer one; the
  channel is a file inside the server's own data directory, so whoever can write it
  already has everything the privilege gated. ``uv run miney check`` no longer has a
  Privilege line. A world where you had run ``/grant somebody miney`` keeps working -
  the grant is simply ignored.
- ``examples/choreography.py`` is gone. It flew several Miney player accounts around in
  formation, and there are no Miney players any more.

v0.7.0
------

A big release of small repairs. Blocks placed away from a player arrived nowhere, event
filters were accepted and ignored, a smooth move looked the wrong way when it landed, and
a script could not be run twice in a row - all of that works now. Uploading and reading
the world got faster, seven new events let a script react to what people do, and the Lua
sandbox no longer hands out the server's file system.

Nothing was removed or renamed, so every call a v0.6.0 script makes still exists. A few
things behave differently, and one of them - the Lua mod on the server has to be the one
that ships with this release - stops a script before it starts. They are listed below.

**Breaking**

Version 0.6.0 is a day old, so the release most people are coming from is 0.5.8. This
section covers everything since then, 0.6.0 included.

- **The Lua mod on the server has to be updated.** The two halves ship together and
  have their own version number, which this release raises. Miney checks it on the first
  call and refuses with a sentence naming the fix, rather than failing somewhere inside
  your own Lua. For a world started with the ``miney`` command that is
  ``uv run miney upgrade``; on somebody else's server the admin updates the mod from
  `ContentDB <https://content.luanti.org/packages/Miney/miney/>`_.
- **Python 3.10 is the minimum version** (since v0.6.0, was 3.6).
- **Event filters are applied now**, and a script written against a version that ignored
  them sees fewer events. ``lt.callbacks.on("chat_message", {"sender_name": "Steve"})``
  used to call the handler for every message from everyone; it now calls it for Steve.
  Registrations that relied on that - a filter written and then worked around in the
  handler - keep working, but a handler that was never told about the filter now runs
  less often. A filter naming a field the event does not carry raises instead of matching
  nothing, and so does a filter value the server cannot compare with ``==``, such as a
  :class:`~miney.Point`.
- **Lua names belong to one connection.** A global assigned in :meth:`~miney.Lua.run` used
  to stay visible to every other script on the server until it restarted; now each
  connection has its own set and it is cleared when the connection ends. A script that
  picked up a value another script had left behind has to pass it on itself -
  :attr:`lt.storage <miney.Luanti.storage>` is the place for that.
- **``getfenv`` is gone from the Lua sandbox**, along with the way it gave to the
  server's real globals and its file system.
- **Lua sent to :meth:`~miney.Lua.run` has an instruction budget.** Code that does not
  return after about a tenth of a second of Lua steps is stopped and comes back as an
  error. It exists because such code used to freeze the whole server. Waiting for the
  engine does not count, so ordinary work is unaffected - a deliberately long computation
  in one call is not, and has to be split.
- **A timer outlives its script no longer.** Anything scheduled with ``minetest.after``
  is cancelled when the connection that asked for it goes. That is what stops a runaway
  animation, and it also means a script cannot arm something and exit expecting it to
  fire.
- **:meth:`lt.nodes.set() <miney.Nodes.set>` raises instead of doing nothing.** A node
  name on its own, or a list with a :class:`~miney.Point` in it, used to be accepted
  silently and place no blocks; it now raises :class:`TypeError`. Code that appeared to
  work and did not will start reporting itself.
- **A second smooth :meth:`~miney.Player.move` replaces the first** instead of running
  alongside it.
- **:meth:`player.move(look_at=...) <miney.Player.move>` tilts the right way.** The
  smooth path measured pitch upwards where Luanti measures it downwards, so a script that
  compensated by negating its own angle has to stop doing that. Without ``smooth`` the
  call raised for every target, so there is nothing to undo there.

**Added**

- Seven more events to subscribe to with :meth:`lt.callbacks.on()
  <miney.callback.Callback.on>`, so a script can react to the world and not only to the
  chat: ``node_dug``, ``node_placed`` and ``node_punched`` for blocks, ``player_dies``,
  ``player_respawns``, ``player_punched`` and ``player_hp_changed`` for the people in it.
  Nothing about the API changes - the event name is a string, filters and handlers work
  as before - and every one of them, with what it carries and when it happens, is
  documented in :mod:`miney.events`.

  The block events carry the position as a :class:`~miney.Point`, so it can be handed
  straight to :meth:`~miney.Nodes.set` or :meth:`~miney.Player.move`. They report what
  the people in the world do: blocks a script writes with :meth:`~miney.Nodes.set` or
  :meth:`~miney.Nodes.fill` send nothing, so a handler that builds cannot set itself
  off.

- :attr:`lt.storage <miney.Luanti.storage>`, the world's key-value store, used like a
  dictionary: ``lt.storage["home"] = "10,20,30"`` is still there the next time the script
  runs, and after a server restart. Keys and values are strings, because that is what
  Luanti stores - use :class:`str` and :mod:`json` on the way in.
- ``storage`` in the :meth:`~miney.Lua.run` sandbox, the same store seen from Lua.
- Miney checks that the Lua mod on the server is new enough to talk to, and says so
  before running anything. The two halves ship together, so they only come apart on a
  server where the mod was installed by hand or from ContentDB and only the Python side
  was updated - and the symptom used to be an error inside your own Lua, naming
  something the old mod had never heard of.

- :meth:`lt.nodes.fill() <miney.Nodes.fill>`, which fills a box with one kind of block
  and does not care how big the box is. Only the two corners and a name go over the
  network, so a floor of four thousand blocks and a hillside of three million cost the
  same to ask for - measured at 4,700,000 blocks a second against
  :meth:`~miney.Nodes.set`'s 700, and a 193x76x193 site levelled in 0.27 seconds. It
  writes blocks and nothing else: no chest inventories, no falling sand, no flowing
  water. :meth:`~miney.Nodes.set` remains the way to place a block that has to work.

- ``wait=True`` on :meth:`~miney.Player.move`, for when the next line needs the player
  to have arrived. A smooth move still returns straight away by default - that is how a
  camera flies over a building site while the building goes on - but the alternative
  used to be ``time.sleep(duration)``, which repeats a number that is already an
  argument and is always slightly too short, because a frame is scheduled for the next
  server step and never sooner.

**Security**

- The Lua sandbox handed out a way back to the server's real globals, and with them the
  file system. ``getfenv`` was part of the sandbox, and Lua defines ``getfenv(0)`` as
  *the global environment*, so ``getfenv(0).io.open(...)`` read and wrote files on the
  machine running the server, ``getfenv(0).x = 1`` was visible to every other script,
  and the per-connection isolation below was decorative. ``getfenv`` is gone from the
  sandbox. It remains true that the ``miney`` privilege means running code inside the
  server - the privilege now says so, and so does the documentation.

**Changed**

- A filter value has to be something the server can compare with ``==`` - a string, a
  number, a boolean, or a list of those - and anything else raises where it was written.
  The value that made this necessary is a position: ``{"pos": Point(1, 2, 3)}`` reads
  like the most obvious filter there is, and the comparison would have rejected every
  event for the rest of the session without a word about why. Ask for the event and
  decide in your own code instead: ``if event.pos.y < 10:``.

- A second :meth:`~miney.Player.move` with ``smooth=True`` on the same player replaces
  the first instead of running alongside it. Two animations both set the position every
  frame, each from the start it remembered, so the player drifted between the two paths
  and reached neither.
- Miney no longer announces itself in the chat. A script connecting and disconnecting
  used to print ``*** Miney joined the game.`` and ``*** Miney left the game.`` to
  everyone on the server, once per run. Messages from real players are untouched.
- :meth:`~miney.Lua.run` documents that Lua globals survive between calls, belong to
  your connection alone, and that the sandbox has no ``_G``.

**Fixed**

- Looking a name up by square brackets works. ``lt.nodes.names["default:dirt"]``,
  ``lt.nodes.names.default["dirt"]``, ``lt.tool[0]`` and every other indexed form raised
  ``AttributeError`` from inside Miney, whichever way round you asked - the lookup read
  something that does not exist. Names now also come back in the same order every time,
  and ``len(lt.nodes.names.default)`` counts that mod's blocks rather than every block in
  the game.

- **Two scripts can drive one world at the same time.** Each ``miney.Luanti()`` already
  got a world of its own to work in - separate variables, separate callbacks, separate
  chat commands - but both send through the same file, and on Windows two scripts
  writing at the same moment could land on top of each other, so one of the two commands
  vanished before the server ever saw it and the script that sent it waited for an
  answer that was never coming. Measured with 300 commands from two scripts at once, 18
  of them disappeared. Miney now takes a lock while it writes, so whichever script gets
  there second waits its turn. Linux was never affected.

- Miney's own player gets up again after it dies. It used to stay dead for the rest of
  the session - a corpse standing where it fell, reporting that position for every
  :attr:`~miney.Player.position` read and refusing to be moved anywhere useful. The
  client does answer the death screen, but the server only accepts an answer to the form
  it is still expecting, and the mod shows its own form for every result and every event,
  including the one announcing the death. Miney now asks the server for the respawn
  through the Lua channel that is open anyway, and hides the player again afterwards if
  the session asked for an invisible one.

- A second world no longer takes the answer away from everything else in the project.
  ``miney.Luanti()``, ``miney start`` and ``miney stop`` used to look only at what was on
  disk, so the moment a second world existed - a test world, a tutorial world, one left
  over from an experiment - every command that had not been told a name gave up with
  *"Several worlds exist"*, and kept giving up after everything was shut down again. They
  now share one rule: the world on the port that was asked for, the only world there is,
  or **the only one that is running**. Starting a world therefore answers the question for
  every command that follows it. When it really cannot be told, the message lists the
  worlds with their status and suggests the one worked in last, rather than the first one
  alphabetically, and ``miney stop`` says which worlds are up instead of quietly stopping
  nothing.

  A bare ``miney start`` in a project with several worlds now opens the one worked in
  last as well. It used to reach for the world named after the default game, which -
  with two worlds already there and neither of them that one - meant **creating a third**:
  a first start, a full map generation and minutes of waiting for a world nobody asked
  for. Creating a world now says so before it happens, and the wait afterwards says
  whether it is generating a map or loading the game's mods, so a normal twenty-second
  VoxeLibre start stops reading like a hang.

- :attr:`player.invisible <miney.Player.invisible>` ``= False`` gives the player back
  what they looked like. It used to put back a guess: a hitbox 2 nodes tall whatever the
  game says - VoxeLibre's is 1.7 - and a model still wearing the transparent texture that
  hid it, so the player stayed invisible while claiming to be visible again. What they
  looked like is now written into their metadata before they are hidden and set back from
  there, so the skin, the model and the real hitbox return. It survives a script that ends
  while its player is hidden, because the note is stored with the player and not in the
  script.

- A chat command whose handler is a callable object works. The dispatcher asked whether
  the handler it had found was *true* rather than whether it was *there*, and an object
  that reports itself empty - a collector, a queue, a counter at zero - answers no. Its
  events were dropped without a word, and because such a handler only stops being empty
  by being called, it stayed silent for the whole run. Plain functions were never
  affected, and neither was the event side of :class:`~miney.callback.Callback`.

- Event filters do something now. ``lt.callbacks.on("chat_message", {"sender_name":
  "Steve"})`` accepted the filter, sent it to the server and the mod dropped it on the
  floor, so the handler ran for every message from everyone and nothing anywhere said
  otherwise. The comparison now happens on the server, before the event is sent, so what
  a filter rejects never travels. A list accepts any one of its values, every named field
  has to match, and a field the event does not carry - ``{"sender": ...}`` for a message
  that has ``sender_name`` - raises and names the fields that exist, instead of silently
  matching nothing. The filter belongs to the handler you registered it with, so you can
  watch the same event twice for two different things and each function only sees what it
  asked for.

- A timer started by your script now ends with your script. Anything scheduled with
  ``minetest.after``, including the animation behind
  :meth:`player.move(smooth=True) <miney.Player.move>`, was handed to the engine and
  then forgotten: it kept running after the script ended, after ``lt.disconnect()`` and
  after the Python process was gone, and since each connection has its own set of Lua
  names, a later script could not even see the variables the loop was built from. Only
  restarting the server stopped it. So ``player.move(..., smooth=True, duration=600)``
  - one typo away from ``60`` - dragged the player for ten minutes, and moving them
  somewhere else did not help: the next frame recomputed the position from the start
  the animation remembered and pulled them back. Every timer now belongs to the
  connection that asked for it, and the server cancels what is left when that
  connection goes, however it goes.

- Uploading is no longer paced by a fixed pause, and a lost packet is no longer lost for
  good. Miney sent reliable packets and never retransmitted them, so it had to send
  slowly enough that nothing was dropped - 495 bytes every 10 milliseconds, about
  45 KB/s, which meant half a minute for a large piece of Lua. Luanti acknowledges every
  reliable packet it accepts and deliberately stays silent about one that arrives too
  early, expecting the sender to try again; Miney now keeps each packet until that
  acknowledgement arrives and resends it if it does not. What limits the rate instead is
  64 packets in flight, so a fast link runs at its own speed and a slow one is throttled
  to a window per round trip. Measured on a local server, with the payload checksummed
  on arrival: 600 KB went from 12.7 seconds to 0.04.

- :meth:`lt.nodes.get() <miney.Nodes.get>` reads a region about thirty times faster,
  and returns exactly what it did before. The time was never in reading the world - it
  was in describing it, one table of five values per node on its way back. A region now
  sends each node name once and collapses runs of identical neighbours, which is what
  terrain mostly is. Reading a 32x32x32 region went from 0.93 seconds to 0.03; a
  24x24x24 one from 0.53 to 0.01. Order, contents and types of the returned list are
  unchanged, checked node by node against the old implementation.

- :meth:`lt.nodes.set() <miney.Nodes.set>` no longer loses blocks that are placed away
  from a player. ``minetest.set_node`` does nothing in a part of the world the server
  does not currently hold in memory - it does not load it and it does not complain - so
  building anywhere nobody was standing produced no blocks, no error and a script that
  reported success. Measured on an unloaded area, none of fifty blocks arrived; all
  fifty do now. The area is loaded first, once per 16x16x16 mapblock rather than once
  per block, so scattered positions cannot ask the server to load everything in between
  them.

- Running a script twice in a row works again. A script that ends without ``with`` never
  disconnected: every namespace on :class:`~miney.Luanti` refers back to it, so it is
  only reachable in a reference cycle, and the collector that could free it is not
  guaranteed to run when the interpreter shuts down. The server therefore kept the
  session open, and the next run was refused with *"Another client is already connected
  with this name."* The disconnect is now registered with :mod:`atexit`, which runs while
  the interpreter is still whole.

- :meth:`player.move(destination=..., look_at=..., smooth=True) <miney.Player.move>`
  arrives looking at the target. The angles were worked out from where the player set
  off instead of where they were going, so the camera finished pointing along the old
  sight line - and the further it flew, the wider it missed. Measured on the demo's
  camera, which flies about a hundred nodes between two acts: 127 degrees off, meaning
  the thing it had flown to see was behind it. It now lands within a hundredth of a
  degree, which is what the instant version already did.

- :meth:`player.move(look_at=...) <miney.Player.move>` aims at the target. Without
  ``smooth`` it called ``set_look_dir``, which Luanti does not have, and raised
  *attempt to call method 'set_look_dir' (a nil value)* for every target; the same call
  made :attr:`~miney.Player.look_dir` impossible to assign. With ``smooth`` it did work,
  but tilted the wrong way: Luanti measures this pitch as positive downwards and the
  angle it was given was positive upwards, so looking 45 degrees up aimed 45 degrees
  down. Both paths now agree and land within a hundredth of a degree.

- :meth:`~miney.Chat.format_message` returns a formatted message instead of raising.
  Both arguments went into the Lua source unquoted, so any message containing a space
  was a syntax error and one without a space silently read two undefined globals.

- A variable assigned in :meth:`~miney.Lua.run` no longer leaks into everybody else's
  scripts. All connections shared one sandbox, so a name assigned by one script stayed
  visible to every other script on the server until it restarted - and overwriting a
  name the sandbox provides, ``minetest = nil``, disabled Miney for the whole server.
  Each connection now has its own set of names, cleared when it ends.

- A Lua loop that never ends no longer freezes the server. Lua sent to
  :meth:`~miney.Lua.run` runs inside the server's own step, so ``while true do end``
  stopped the world for everybody until somebody killed the process, losing whatever had
  not been saved. Such a loop is now stopped after about a tenth of a second and comes
  back as an error that says what happened. Scripts that do real work are unaffected -
  the count is of Lua steps, and waiting for the engine is not one.

- :meth:`~miney.Lua.run` says so when the code is too long instead of timing out. The
  server silently drops anything over 640 KB, so a large snippet spent the full timeout
  waiting for an answer that was never coming, then reported only *Timeout*.

- Strings containing control characters no longer fail with a Lua syntax error.
  ``lt.chat.send_to_all("hello\x00world")`` answered *invalid escape sequence* at anyone
  who had never written a line of Lua, because the value was escaped the way JSON does
  it and Lua has no ``\u`` escape. Affected every value on its way into Lua, so also
  node names, player names and chat commands.

- :meth:`lt.nodes.set() <miney.Nodes.set>` accepts any collection of nodes - a tuple, a
  set, a generator - and says so when it is handed something else. It used to check for
  a :class:`list` exactly, and do nothing at all for anything that was not one: a tuple
  looks like the documented call, placed no blocks, raised nothing and returned nothing.
  A subclass of :class:`~miney.node.Node` was refused for the same reason. Passing a
  node name on its own, or a list with a :class:`~miney.point.Point` in it, now raises a
  :class:`TypeError` naming what arrived and showing the call that works.

- :meth:`lt.nodes.get() <miney.Nodes.get>` explains itself instead of returning
  ``None``. Anything that was not a point or a pair of points fell off the end of the
  function, so asking for three corners of a cuboid - a reasonable thing to try - gave
  back nothing at all.

- :class:`~miney.inventory.Inventory` raises when it belongs to neither a player nor a
  node. All four of its methods asked what they were attached to, and returned ``None``
  or an empty list for anything else, so a wrongly built inventory was indistinguishable
  from an empty one.

- :class:`~miney.Inventory` quotes what it is given. The item name, the amount, the
  player name and the inventory list name all went into the Lua source as-is, so an item
  name containing a quote either failed with a Lua syntax error or ran as Lua - the same
  hole that :meth:`~miney.Chat.format_message` had. All four now go through
  :meth:`~miney.Lua.dumps`.

- :meth:`~miney.Inventory.get_list` and :meth:`~miney.Inventory.get_lists` return an
  empty list for an empty inventory instead of ``None``. An empty Lua table arrives on
  the Python side as ``None``, so looping over the contents of an empty chest raised
  *'NoneType' object is not iterable*. ``get_list()`` also documents what it really
  returns: the occupied slots, not one entry per slot.

- ``lt.players["Nobody"]`` raises :class:`~miney.exceptions.PlayerNotFoundError` and
  lists who *is* online, which is nearly always the next question. It used to raise
  ``IndexError("unknown player")``. The new exception is a subclass of ``IndexError``,
  so scripts catching the old one keep working.

v0.6.0
------

The ``miney`` command. Getting from "I have Python" to "a player moves in a 3D world"
no longer means installing and configuring Luanti by hand.

**Added**

- The ``miney`` command line tool, managing a project-local Luanti environment:
  ``init``, ``start``, ``stop``, ``status``, ``logs`` and ``remove``.
- ``miney check`` verifies that Python can drive Luanti and offers to fix what it finds.
- ``miney upgrade`` updates Miney, its Lua mod and Luanti itself.
- ``miney init`` downloads Luanti on Linux as a pkgforge AppImage.
- Games are installed from `ContentDB <https://content.luanti.org>`_.
- Tools, ``Vector``, the privilege list and the connection errors have API documentation for
  the first time.

**Changed**

- Python 3.10 is the minimum version.
- The quickstart is written around ``uv`` and the ``miney`` command, and is now four short
  steps. Everything it used to hide in dropdowns moved to a new *Installation in detail*
  page, and exploring Miney in the Python shell moved to *Basics*.
- The roadmap moved out of the documentation into ``TODO.md``.

**Fixed**

- A normal first login no longer prints a stack trace.
- The API documentation showed a ``lt.players.list()`` method that never existed. Use
  ``lt.players`` directly â€” it iterates, counts and indexes like a list.
- Around twenty cross-references in the API documentation pointed at nothing and rendered
  as dead text.

v0.5.8
------

Callbacks and events. The is also the first version where we track code changes.

**Added**

- Added ``Callback`` and ``Events``.
- Added chat event and chat command handling with decorators and procedural registration.
- Added tests with pytest.
- A project changelog to the documentation.

**Changed**

- ``invisible`` is the new default for the miney player.

v0.5.0
------

With version 0.5 we removed mineysocket and talking now directly to the server over the Luanti protocol.

