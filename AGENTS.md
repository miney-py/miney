# Miney — agent notes

Python interface to [Luanti](https://www.luanti.org/) (formerly Minetest). Two halves that must stay in sync:

- `miney/luanticlient/` — a from-scratch implementation of the Luanti **client** network protocol (UDP, SRP auth, packet builders). Miney logs into the server as a real player account.
- `miney/mod_data/miney/` — the server-side Lua mod that receives commands and fires callbacks, shipped inside the wheel so an installed Miney always carries a matching copy. Requires Luanti 5.7+.
- `miney/` (rest) — the user-facing API: `Luanti`, `Player`, `Nodes`, `Chat`, `Lua`, `Callback`, `Point`/`Vector`.

Changing a wire message, command name or callback payload usually means touching **both** the Python side and the Lua mod.

## What Miney is for

Miney is an education project: people use it to **learn Python**, with Luanti as the playground. There are exactly two things a user does with it:

1. **Drive the world** — move a player, place nodes, change the time of day. Often from the REPL, but scripts count too.
2. **React to the world** — callbacks and chat commands, when something happens in the game.

The first is where beginners start, and it is where the library must be at its best: teleporting a player based on a simple `if`, spawning a wall of blocks with a `for` loop. These are first-week Python concepts, and Miney's job is to make them the shortest path to something visible in a 3D world. Reacting to the world (`lt.callbacks`, `@lt.chat.command`) is the advanced half — real, supported, but not what day one looks like.

The public API is often the first library API a beginner ever reads. That makes API design and docstrings a primary feature, not polish applied afterwards. A feature that isn't itself educational is fine to add — infrastructure, performance, protocol internals, tooling. The rule is only that it must not make the learning surface worse: keep it out of the top-level namespace, off the beginner's happy path, and out of the introductory docs. Advanced escape hatches are welcome as long as nobody trips over them on day one.

**The project stays small and well-structured on purpose. A coherent library with a clear direction beats a big pile of features. When in doubt, leave it out — a feature that would need a confusing API has been dropped before and can be dropped again.**

When a clean API and an easy implementation conflict, the API wins and the complexity goes inside the library.

## API rules

These are not aspirations — they describe how the existing code already works. Follow them so the library stays one coherent thing.

**Structure**

- **One entry point.** `Luanti` is the façade; everything hangs off it as a property: `lt.chat`, `lt.nodes`, `lt.players`, `lt.lua`, `lt.tool`, `lt.callbacks`. A new capability becomes a property on an existing namespace, never an object the user has to construct and wire up themselves.
- **Keep the set of user-constructible classes tiny.** Today it is `Luanti`, `Point`, `Node`. Everything else (`Chat`, `Nodes`, `Inventory`, `PrivilegeManager`, the `*Iterable` helpers) is reached through a property and says so in its docstring. Every additional class in that set is one more concept in the learner's head.
- **Properties for state, methods for actions.** `player.speed = 5`, `lt.time_of_day = 0.5` versus `chat.send_to_all(...)`, `nodes.set(...)`. It should read like a sentence.
- **Expose the intent, hide the mechanism.** `player.fly = True` instead of teaching the privilege system; `player.creative` hides the VoxeLibre (mineclone2) `mcl_gamemode` versus privilege split. The mechanism stays reachable one level down (`player.privileges`, `lt.lua.run()`) for whoever wants it.
- **Behave like the builtins the learner already knows.** `Point` supports `+ - * /`, `len()`, iteration and indexing; `PrivilegeManager` behaves like a list (`in`, `append`, `remove`); `Luanti` is a context manager. Prefer implementing the right dunder over inventing a method name.
- **Every user-visible class gets a `__repr__`.** `<Luanti Player "Steve">`, `<Players: [...]>`. The REPL echo is a teaching channel.
- **Autocomplete is didactics, not comfort.** `lt.nodes.names.default.dirt` and `lt.tool.default.pick_mese` exist so the node/tool strings are discoverable with TAB instead of memorized. That machinery is worth its weight; keep new string-y APIs discoverable the same way.
- **Offer a plain-function twin for every decorator.** `@lt.chat.command()` next to `chat.register_command()`, `@lt.callbacks.on()` next to `lt.on_event()`. Decorators are advanced syntax; a beginner must not be forced through them.

**One function per concept, with optional depth**

`Player.move()` is the model to copy. There is one obvious action — `player.move(destination=Point(10, 20, 30))` — and the extra parameters (`look_at`, `yaw`, `pitch`, `smooth`, `duration`, `step_interval`) refine that same concept without becoming five separate method names. This only works if:

- the important parameters come **first**, and everything after them can be omitted;
- the simplest call is genuinely one line with one argument;
- the docstring opens with numbered examples that go from trivial to advanced;
- conflicting combinations raise a `ValueError` that names the conflict.

**Aliases are allowed on top of the general function, never instead of it.** `teleport()`, `look_at()`, `fly_to()` and `turn()` are welcome as thin wrappers around `move()` — a beginner searching for "teleport" should find something. The conditions:

- the alias delegates to the general function, it does not reimplement it;
- its docstring points at the general function and **shows the equivalent call**, so the alias teaches `move()` instead of hiding it;
- the general function stays the documented centre of the concept.

What is not allowed is splitting one concept into four peer functions with no centre.

**Errors and input**

- **Convenience where the intent is obvious, strictness where it is not.** Output-direction calls may coerce: `chat.send_to_all(42)` converts to `"42"`, because there is exactly one thing the user could have meant. State-changing calls do not guess: `player.hp = "twenty"` raises, because there is no sensible conversion and getting it wrong teaches the wrong thing. Meeting the user halfway is fine; inventing their intent is not.
- **Validate in the setter and name the valid form.** `"Time value has to be between 0 and 1."`, `'Use a dict in the form: {"h": 1.1, "v": 1.1}'`. The message shows what *is* accepted, not just that the input was wrong.
- **Never fail silently.** No branch that quietly does nothing for an unexpected type, no `return None` that hides bad input.
- **Raise a specific exception from `miney/exceptions.py`.** A raw `KeyError`, `AttributeError` or protocol-level exception must never surface to the user.
- **A broken user callback must not kill the session.** Handler exceptions are logged, not propagated (`miney/callback.py`).
- **Everything crossing into Lua goes through `lua.dumps()`.** Never f-string a user value straight into Lua source.

**Docstrings**

- **Type hints on everything public.** They drive IDE autocomplete, which is how beginners explore.
- **Document the trap, not the signature.** `Player.position` explains that you add 0.5 to `y` so the feet touch the node, and that a player needs two blocks of headroom or gets stuck. That is knowledge nobody derives from the type. The signature documents itself; the pitfall does not.
- **A runnable example, or it isn't finished.** Copy-pasteable into a beginner's script and actually working.

## Docs must render well with Sphinx autodoc

The published documentation is generated from the code (`docs/`, autodoc + `viewcode` + `intersphinx`, published to readthedocs). Good docs are a headline feature of this project, and they only exist if the code is written for the generator:

- **reST field syntax only.** There is no `napoleon` extension configured — Google- and NumPy-style docstrings render as raw text. Use `:param x:`, `:return:`, `:rtype:`, `:raises X:`.
- **No docstring means no documentation.** `docs/api/*.rst` uses `.. autoclass:: :members:`, which skips undocumented members entirely. An undocumented public property is invisible to users, not merely terse.
- **Document public names as `miney.Thing`.** The `.rst` files reference the re-exported name (`.. autoclass:: miney.Player`), so a new public class must be exported in `miney/__init__.py` and listed in `__all__` or autodoc cannot find it.
- **Members render alphabetically** (`autodoc_default_options` in `docs/conf.py`), so source order carries no teaching narrative. The narrative lives in the prose above the `autoclass` directive in the `.rst` file — write it there.
- **A new public class needs its own `docs/api/<name>.rst` and a `toctree` entry**, otherwise it never appears in the docs.
- **Cross-link with `:class:`~miney.player.Player`` / `:attr:` / `:meth:`.** The `~` keeps the rendered label short.
- **Use attribute docstrings for documented instance attributes** — a string literal directly after the assignment, as `Player.inventory` does.
- **Check the rendered output for anything non-trivial**, especially code blocks and examples: `cd docs && make html`. Build into the normal `docs/_build/html/` and **leave the result on disk** — Robert opens those files to look at the rendered pages. Do not build into a throwaway directory and do not clean up afterwards. `docs/_build/` is gitignored, so it never ends up in a commit.
- **The build must finish with zero warnings.** A broken cross-reference or a short title underline is a rendering bug, not noise.

## Working agreement

- Work happens on `dev`. `master` gets changes via PR. Don't commit to `master` directly.
- Public API is re-exported in `miney/__init__.py` and listed in `__all__` — new public names belong in both.
- Version is `__version__` in `miney/__init__.py`; `pyproject.toml` reads it statically via `[tool.setuptools.dynamic]`. There is no second place to bump.

## Tests

```
pytest
```

Config in `pytest.ini`: `--strict-markers --maxfail=1` plus coverage — the run stops at the first failure by design.

Tests never talk to a real Luanti server. They use stubs and a protocol emulation (`tests/conftest.py`, `test_lua_mockserver.py`, `test_client_protocol_emulation.py`). Keep it that way; a new feature needs a test that works offline.

CI (`.github/workflows/ci.yml`) runs `pytest` on Ubuntu for every pull request and every push to `master`.

## Don't touch

`build/`, `dist/`, `miney.egg-info/`, `venv/`, `tmp/`, `.idea/` — all generated or local-only.
