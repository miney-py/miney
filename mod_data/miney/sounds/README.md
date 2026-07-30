# Bundled sounds

47 sound effects, so that `lt.sound.play(...)` has something to play on any server, in
any game, without anybody having to find a name the game happens to ship.

They are named `miney_<something>.ogg` and reached from Python by that name without the
extension:

```python
lt.sound.play("miney_power_up_1")
lt.sound.play(lt.assets.sounds.miney.power_up_1)   # the same name, found with TAB
```

## Credit

**Digital Audio** by **Kenney Vleugels** — <https://kenney.nl/assets/digital-audio>

Released under [Creative Commons Zero (CC0 1.0)](http://creativecommons.org/publicdomain/zero/1.0/):
free for personal and commercial use, credit appreciated but not required. Kenney gets it
here anyway, because the pack is good and somebody should say so.

Support Kenney: <https://support.kenney.nl>

## What changed from the original pack

- **Renamed.** Luanti media names are global across every mod on a server, so each file
  carries a `miney_` prefix; `phaserUp1.ogg` would have collided with the next mod that
  had one. The camel case became snake case at the same time, because the names turn into
  Python attributes in `lt.assets.sounds`.
- **The stereo files were left out.** Luanti positions single-channel audio only
  (`doc/lua_api.md`: *"For positional playing of sounds, only single-channel (mono) files
  are supported"*), and a stereo file passed to `point=` or `follow=` would quietly play
  flat, from everywhere, with no warning anybody could act on. The 15 dropped files are
  `phaseJump1-5`, `phaserDown1-3` and `phaserUp1-7`; everything shipped here works at a
  point.
- **`Preview.ogg` was left out** — it is a 600 KB montage of the whole pack, twice the
  size of every sound in it put together.

The audio itself is untouched: the original Ogg Vorbis files, byte for byte.

## The Miney mod is LGPL, these are not

The licence in `../LICENSE.txt` covers the mod's code. These sound files are CC0 and stay
CC0 wherever they go.
