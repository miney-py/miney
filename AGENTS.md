# Miney — agent notes

Python interface to [Luanti](https://www.luanti.org/) (formerly Minetest). Two halves that must stay in sync:

- `miney/luanticlient/` — a from-scratch implementation of the Luanti **client** network protocol (UDP, SRP auth, packet builders). Miney logs into the server as a real player account.
- `mod_data/miney/` — the server-side Lua mod that receives commands and fires callbacks. It lives at the repo root, not inside the `miney/` Python package, but ships in the wheel as its own top-level `mod_data` package so an installed Miney always carries a matching copy. Requires Luanti 5.9+.
- `miney/` (rest) — the user-facing API: `Luanti`, `Player`, `Nodes`, `Chat`, `Lua`, `Callback`, `Point`/`Vector`.

Changing a wire message, command name or callback payload usually means touching **both** the Python side and the Lua mod.

## Look it up in `luanti-src/`

A checkout of the Luanti sources normally sits at `luanti-src/` in the repo root. It is
gitignored, so it is reference material and never part of a commit — but when it is
there, **read it instead of recalling what the engine does**:

- `luanti-src/doc/lua_api.md` — the modding API. The authority on every field name,
  every default and every "added in 5.x" note the mod half depends on.
- `luanti-src/src/` — the C++ engine. Where to go when the Lua docs describe *what* but
  the question is *what actually happens*: packet layout for `miney/luanticlient/`,
  limits the docs do not name, whether a file survives a restart.
- `luanti-src/src/defaultsettings.cpp` — what a setting really defaults to.

Version-gated behaviour is worth checking twice: the checkout tracks a recent release
(5.16 at the time of writing) while Miney supports back to 5.9, so a feature documented
there may not exist on the oldest server Miney talks to. `core.get_version()` and the
`core.features` table in `lua_api.md` say when something appeared.

If `luanti-src/` is missing, an installed Luanti carries the same `doc/lua_api.md` — in
a Miney-managed install that is `~/Luanti/doc/lua_api.md`. The C++ sources are only in
the checkout.

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
- **Check the rendered output for anything non-trivial**, especially code blocks and examples. Build into the normal `docs/_build/html/` and **leave the result on disk** — Robert opens those files to look at the rendered pages. Do not build into a throwaway directory and do not clean up afterwards. `docs/_build/` is gitignored, so it never ends up in a commit.

  ```
  uv run --group docs sphinx-build -E -W --keep-going -b html docs docs/_build/html
  ```

  `cd docs && make html` is the documented incantation everywhere else and does **not** work here: Windows has no `make`, and `make.bat` looks for `sphinx-build` on the PATH while it lives in the uv environment. Go through `uv run`.
- **The build must finish with zero warnings.** A short title underline or an unknown directive is a rendering bug, not noise.
- **Zero warnings does not mean the cross-references resolve.** A `:class:`/`:attr:`/`:meth:` pointing at nothing renders as plain grey text and passes `-W` silently. Only `-n` reports it, so run that too whenever you touch docstrings or `docs/api/*.rst`:

  ```
  uv run --group docs sphinx-build -E -n -b html docs docs/_build/html
  ```

  Twenty dead references accumulated behind a clean `-W` build before anyone noticed. Two get reported that cannot be fixed from prose (`callable`, `LuantiClient` in type annotations) — everything beyond those two is a real broken link.

## How the docs read

The generator rules above decide whether a page renders. These decide whether a beginner
gets through it. The reader is someone learning Python who may not know what a terminal
is — write for them, and the experienced reader is fine too.

- **Two layers per topic, and the short one stays short.** `getting_started/quickstart.rst`
  is the happy path and nothing else; `getting_started/installation.rst` catches every
  "but what if". New depth goes to the detail page. A quickstart that grows is a quickstart
  that stopped working.
- **Answer "what do I type" before "why it works".** The explanation goes after the command,
  or into the detail page — never in front of it.
- **End on something visible.** A snippet that connects and stops teaches nothing. The
  quickstart's first script writes into the chat and moves the sun, because a beginner needs
  to see the world react. Every page-closing example should pay off that way.
- **Never leave a reader without a next step.** Close a page with a link, or with a
  `grid-item-card` set when there is more than one sensible direction.
- **Emoji in section headings, octicons in the body.** Emoji are stripped from the anchor
  (`🧰 Step 1: Install uv` → `#step-1-install-uv`) and show up in the sidebar. An
  `:octicon:` in a heading builds the anchor id out of the SVG markup and ruins it — use
  those in card titles, admonition titles and inline text only. One icon per heading.
- **Not everything is a dropdown.** A page made of collapsed boxes is a page nobody opens.
  `.. dropdown::` is for a genuine aside next to the main flow; anything a reader might
  come looking for gets a real section on the detail page.
- **Show commands the way the reader types them**, `uv run miney start`, not `miney start`,
  and keep that prefix consistent across every page.
- **Verify every example against the source before it ships.** Method names, `__repr__`
  output and accepted value ranges — `lt.players.list()` sat in the API docs for a long
  time without ever having existed.
- **Second person, present tense, one idea per sentence.** "You install the library, and
  Miney brings Luanti along." Name the trap where the reader will hit it, in an
  `.. important::` or `.. warning::`, not three paragraphs earlier.

## Working agreement

- Work happens on `dev`. `master` gets changes via PR. Don't commit to `master` directly.
- Public API is re-exported in `miney/__init__.py` and listed in `__all__` — new public names belong in both.
- Version is `__version__` in `miney/__init__.py`; `pyproject.toml` reads it statically via `[tool.setuptools.dynamic]`. There is no second place to bump.
- The two halves have their own contract number, and it is **not** the release version:
  `MOD_API` in `mod_data/miney/init.lua` and `REQUIRED_MOD_API` in `miney/lua.py`. The
  mod sends its number with every answer and `Lua.run` refuses anything older, so a
  server still carrying last year's mod gets a sentence telling it to update instead of
  a nil index deep inside somebody's script. Raise both together when a command, a
  field or a name in the sandbox changes so that an older Python would not survive it —
  and leave them alone at release time. `mod.conf` is not an option for this: Luanti's
  spec has no `version` field, and its `release` belongs to ContentDB.
- Every user-visible change gets a `docs/changelog.rst` entry under the *unreleased* version heading — added, changed, fixed. Write it in the same commit as the change, not at release time. Internal refactoring, tests and tooling stay out; the changelog is read by users, not by us.

## Releases

Publishing a GitHub release publishes Miney everywhere. `.github/workflows/release.yml`
runs on `release: published`, checks the tag against `miney.__version__`, builds, pushes
to PyPI (Trusted Publishing, no token stored) and then creates the ContentDB release from
the same tag. The GitHub release body becomes the ContentDB release notes verbatim.

Tags are `v0.6.0`. PyPI gets `0.6.0` — the workflow strips the `v`.

The ContentDB half uploads `mod_data/miney/` as a zip and does **not** use ContentDB's
`method: git`. That method clones the repository and expects a mod at its root; our mod
sits in `mod_data/`, and neither the API nor `.cdb.json` has a field to point at a
subdirectory. A git release therefore fails asynchronously with *"Expected a mod or
modpack, found unknown"* — the API call itself returns `success: true`, so nothing goes
red. If a release ever looks fine but no new version shows up on ContentDB, open the
task URL from the API response; that is where the real error is.

Release titles are unique per package on ContentDB, and a failed import keeps its name.
Retrying after a failure gives `{"error":"A release with this name already exists"}` until
the broken release is deleted by hand at
`https://content.luanti.org/packages/Miney/miney/releases/`. A release with `size: 0` and
`url: null` in the API listing is one of those corpses.

A release is a pull request plus one command:

1. On `dev`: bump `__version__` in `miney/__init__.py`, give `docs/changelog.rst` its
   version heading, and check that the entries match what actually changed.
2. `uv run pytest` and `cd docs && make html` — both clean.
3. Open the PR from `dev` to `master`, wait for CI, merge it.
4. `gh release create v0.6.0 --target master --title "v0.6.0" --notes-file <notes>` —
   the notes are the changelog section for this version, in Markdown.

Nothing else triggers a publish. Pushing a tag does not, merging to `master` does not.

The workflow file has to live on `master` for the release event to fire at all — that is a
GitHub rule for repository-level events. But the version that actually *runs* is the one
in **the commit the tag points at**, not the current `master`. Both together give one
rule: tag a commit of `master` that already contains the workflow you want to run.

That is why the pull request comes first and `gh release create` second. It also means a
workflow fix does not reach an existing tag: merging the fix to `master` changes nothing
for `v0.6.0`, because that tag still points at the commit before it. Re-tagging is the
only way, and it is only acceptable while nothing but the workflow has changed — check
with `git diff --stat <tag>..master -- miney/ mod_data/ pyproject.toml` and expect it to
be empty.

Editing `release.yml` has one trap worth remembering: naming **any** entry under
`permissions:` sets every unnamed scope to `none`. Adding `id-token: write` for PyPI
therefore silently removes the `contents: read` that `actions/checkout` needs. List both.

There is no way to rehearse a release. The workflow only ever runs on a real
`release: published` event, so the safety net is the version guard and the publish order,
not a dry run.

If a run fails: the version guard runs before every publish and PyPI before ContentDB, so
a failure leaves the later registries untouched. Fix the cause, then delete the GitHub
release and create it again on the same tag — that fires a fresh `release: published`
event, and GitHub reads the workflow from `master`, so the re-run picks up the fix. PyPI
is set to `skip-existing`, so an already-published version is skipped rather than failing
the run. Only delete the tag as well if the code itself has to change.

## Tests

```
uv sync      # once - installs the "dev" dependency group
uv run pytest
```

The tooling lives in `[dependency-groups]` in `pyproject.toml`: `dev` (pytest), `docs`
(Sphinx, `uv sync --group docs`) and `release` (build/twine). Groups are not part of the
wheel, so none of it reaches a Miney user. Miney itself has no runtime dependencies —
the package imports the standard library only, and that is worth keeping.

Config in `pytest.ini`: `--strict-markers --maxfail=1` plus coverage — the run stops at the first failure by design.

Tests never talk to a real Luanti server. They use stubs and a protocol emulation (`tests/conftest.py`, `test_lua_mockserver.py`, `test_client_protocol_emulation.py`). Keep it that way; a new feature needs a test that works offline.

CI (`.github/workflows/ci.yml`) runs `pytest` on Ubuntu for every pull request and every push to `master`.

## Don't touch

`build/`, `dist/`, `miney.egg-info/`, `venv/`, `tmp/`, `.idea/` — all generated or local-only.
