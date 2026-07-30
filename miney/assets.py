"""
Pictures and sounds: the ones the game already has, and the ones you make yourself.
"""
import base64
import hashlib
import io
import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .exceptions import AssetError, AssetTimeout, PlayerOffline
from .nodes import NameIterable

if TYPE_CHECKING:
    from .luanti import Luanti
    from .player import Player


logger = logging.getLogger(__name__)

#: The largest picture one :meth:`~miney.Assets.upload` call will send, in bytes.
#:
#: It travels over the same connection as the game, so a big one is felt as a stutter
#: by whoever receives it. A drawn or plotted picture is nowhere near this; a photo
#: straight out of a camera is.
MAX_UPLOAD = 4 * 1024 * 1024

#: How long :meth:`~miney.Assets.upload` waits between two questions to the server
#: while the picture is on its way.
POLL_INTERVAL = 0.2

#: What the first bytes of a file say it is. Luanti goes by the file extension, so the
#: name Miney invents has to carry the right one.
_MAGIC = ((b"\x89PNG", "png"), (b"\xff\xd8\xff", "jpg"), (b"OggS", "ogg"))

#: The same thing for a :class:`~pathlib.Path`, which is trusted to be named correctly.
_SUFFIXES = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg", ".ogg": "ogg"}

#: What a ``name=`` of your own may look like. It becomes a file on the server with
#: ``keep=True``, so the mod checks this again - never trust the client with a path.
_NAME = re.compile(r"^[A-Za-z0-9._\-]+\.(?i:png|jpe?g|ogg)$")

#: What the mod's ``kind`` field turns into on this side. Anything else is an
#: :class:`~miney.exceptions.AssetError`.
_ERROR_KINDS = {"limit": ValueError, "offline": PlayerOffline}


def _read(image: Any) -> tuple[bytes, str]:
    """
    Turn whatever was handed to :meth:`Assets.upload` into bytes and a format.

    Matplotlib and Pillow are recognised by the method they carry, never imported:
    Miney has no runtime dependencies, and two attribute checks work for anything
    shaped the same way.

    :param image: Bytes, a :class:`~pathlib.Path`, a matplotlib figure, a Pillow image
        or an open file.
    :return: The file's bytes, and ``"png"``, ``"jpg"`` or ``"ogg"``.
    :raises TypeError: If a :class:`str` was given, which is a name and not a file.
    :raises ValueError: If the format is not one Miney can send.
    """
    if isinstance(image, str):
        raise TypeError(
            f"A string is the name of something the server already has, not a file to "
            f'upload. Use Path("{image}") if you meant the file on your computer.'
        )

    if isinstance(image, Path):
        suffix = image.suffix.lower()
        if suffix not in _SUFFIXES:
            raise ValueError(
                f"Miney uploads PNG and JPEG pictures and Ogg sounds, and "
                f"{image.name!r} is none of them. Save it as .png or .ogg and try "
                f"again."
            )
        return image.read_bytes(), _SUFFIXES[suffix]

    if isinstance(image, (bytes, bytearray)):
        data = bytes(image)
    elif hasattr(image, "savefig"):  # a matplotlib Figure
        buffer = io.BytesIO()
        image.savefig(buffer, format="png")
        data = buffer.getvalue()
    elif hasattr(image, "save"):  # a Pillow Image
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        data = buffer.getvalue()
    elif hasattr(image, "read"):
        data = image.read()
    else:
        raise TypeError(
            f"Miney cannot read a {type(image).__name__} as a file. Give it bytes, "
            f"a Path, an open file, a Pillow image or a matplotlib figure."
        )

    for magic, kind in _MAGIC:
        if data.startswith(magic):
            return data, kind
    raise ValueError(
        "Miney uploads PNG and JPEG pictures and Ogg sounds, and this is none of "
        "them - its first bytes match no format Miney knows."
    )


def _tree(by_mod: dict) -> NameIterable:
    """
    Turn the ``mod -> names`` table the server sends into something TAB completes.

    Each tree carries its own flat list of names, because that is what iterating one and
    :func:`len` read. Sharing a single list between the textures and the sounds would
    make either of them answer with both.

    :param by_mod: What the mod's ``textures()`` or ``sounds()`` returned.
    :return: The root, with one :class:`~miney.nodes.NameIterable` per mod below it.
    """
    flat: list[str] = []
    root = NameIterable()
    for mod, names in sorted(by_mod.items()):
        # Built empty and filled here rather than by the constructor: a media name is
        # 'default_dirt.png', not 'default:dirt', so the mod it belongs to cannot be
        # read off the name and has to come from the table the server sent.
        group = NameIterable()
        group._names = sorted(names)
        for name in names:
            flat.append(name)
            setattr(group, _short_name(mod, name), name)
        setattr(root, mod, group)
    root._names = sorted(flat)
    return root


class Assets:
    """
    Pictures and sounds: what the game already has, and what you make yourself.

    Luanti calls all of this **media**, which is the word to search for in its own
    documentation and on the forums.

    You do not create this class yourself, it is reached through
    :attr:`~miney.Luanti.assets`.

    **Finding what the game ships.** Every name is one TAB away, the same way
    :attr:`lt.nodes.names <miney.Nodes.names>` works for blocks::

        >>> lt.assets.textures.default.dirt
        'default_dirt.png'
        >>> lt.assets.sounds.default.dig_stone
        'default_dig_stone'

    **Getting your own in.** Anything Python can draw, and any Ogg file you have::

        >>> from pathlib import Path
        >>> name = lt.assets.upload(Path("cat.png"))
        >>> lt.players.Steve.hud.image(name)
        >>> lt.sound.play(lt.assets.upload(Path("fanfare.ogg")))

    .. important::

       What you upload is gone when the server stops, unless you pass ``keep=True``. And
       it travels over the same connection as the game, so a big one is felt as a
       stutter by whoever receives it.
    """

    def __init__(self, luanti: "Luanti"):
        """
        :param luanti: The parent :class:`~miney.Luanti` object.
        """
        self.lt = luanti
        self._textures: NameIterable | None = None
        self._sounds: NameIterable | None = None

    def __repr__(self) -> str:
        return "<Luanti Assets>"

    @property
    def textures(self) -> NameIterable:
        """
        Every texture the server's mods carry, grouped by the mod they came from.

        A texture name is a plain string like ``'default_dirt.png'``, and nothing in
        Luanti tells you which ones exist - a name that does not exist simply draws
        nothing. So they are here to be found with TAB instead of memorised::

            >>> lt.assets.textures.default.dirt
            'default_dirt.png'
            >>> lt.assets.textures.mcl_core.stone
            'mcl_core_stone.png'

        Iterating gives every name the server has::

            >>> len(lt.assets.textures)
            2317
            >>> list(lt.assets.textures)[:2]
            ['default_dirt.png', 'default_stone.png']

        .. note::

           This is read from the server the first time you touch it, and kept. It is
           also not complete: it covers the mods' own textures, and a game can draw
           with pictures Miney never sees. So Miney never refuses a name because it is
           missing here - if a texture stays invisible, check its spelling.

        :return: The names, grouped by mod. See the examples above.
        """
        if self._textures is None:
            by_mod = self.lt.lua.run("return miney_assets.textures()")
            # An empty Lua table comes back as an empty list, not as an empty object.
            self._textures = _tree(by_mod if isinstance(by_mod, dict) else {})
        return self._textures

    @property
    def sounds(self) -> NameIterable:
        """
        Every sound the server's mods carry, grouped by the mod they came from.

        These are what :meth:`lt.sound.play() <miney.Sound.play>` takes, and like a
        texture name nothing in Luanti tells you which ones exist - so they are here to
        be found with TAB instead of guessed::

            >>> lt.assets.sounds.default.dig_stone
            'default_dig_stone'
            >>> lt.assets.sounds.miney.power_up_1
            'miney_power_up_1'
            >>> lt.sound.play(lt.assets.sounds.miney.power_up_1)

        Iterating gives every sound the server has::

            >>> len(lt.assets.sounds)
            412

        .. note::

           A sound name is not a file name. ``default_dig_stone`` is played by that
           name, and the game may hold it as ``default_dig_stone.ogg`` or as a whole set
           of ``default_dig_stone.0.ogg`` to ``.9.ogg`` - one of which is picked at
           random every time. Miney lists the name, not the files.

        This is read from the server the first time you touch it, and kept.

        :return: The names, grouped by mod. See the examples above.
        """
        if self._sounds is None:
            by_mod = self.lt.lua.run("return miney_assets.sounds()")
            self._sounds = _tree(by_mod if isinstance(by_mod, dict) else {})
        return self._sounds

    def upload(self, image: Any, name: str = None,
               player: "Player | str" = None, keep: bool = False,
               timeout: float = 30) -> str:
        """
        Put a picture or a sound on the server and give back the name it is usable
        under.

        That name goes anywhere a texture name goes - a HUD image, a statbar, a node's
        texture - and an uploaded Ogg goes to :meth:`lt.sound.play()
        <miney.Sound.play>`:

        1. A file from your computer::

            >>> from pathlib import Path
            >>> name = lt.assets.upload(Path("cat.png"))
            >>> name
            'miney_3f9a1c7b2e04.png'
            >>> lt.players.Steve.hud.image(name)

        2. Something you drew or plotted, without saving it first::

            >>> lt.assets.upload(figure)          # a matplotlib figure
            >>> lt.assets.upload(pil_image)       # a Pillow image
            >>> lt.assets.upload(png_bytes)       # raw bytes

        3. Your own music::

            >>> lt.sound.play(lt.assets.upload(Path("fanfare.ogg")))

        4. For one player only, and forgotten again once they have it. This is the one
           to use for a picture that changes, because nothing piles up::

            >>> lt.assets.upload(chart, player=lt.players.Steve)

        5. Still there after the server restarts::

            >>> lt.assets.upload(logo, keep=True)

        .. important::

           **The name is a hash of the file**, so uploading the same one twice costs
           nothing - and a *changed* picture gets a *different* name. That is not a
           quirk: Luanti refuses to know the same name twice, so a chart that updates
           cannot keep its old name. Whatever shows the picture has to be told the new
           one.

        This call comes back only once the file has really arrived on the client, so the
        next line can use the name straight away. A 800x600 chart is 40-80 KB and
        arrives without anybody noticing; a minute of Ogg is closer to a megabyte, so
        that one is worth uploading before the show rather than during it.

        .. note::

           A sound is uploaded as ``miney_3f9a1c7b2e04.ogg`` and *played* as
           ``miney_3f9a1c7b2e04``, without the extension.
           :meth:`lt.sound.play() <miney.Sound.play>` drops it for you, so the name can
           go straight from here to there.

        :param image: The file: :class:`bytes`, a :class:`~pathlib.Path`, an open file,
            a Pillow image or a matplotlib figure. A :class:`str` is *not* a file, it is
            the name of one the server already has.
        :param name: A name of your own instead of the hash. Letters, digits, ``.``,
            ``-`` and ``_``, ending in ``.png``, ``.jpg`` or ``.ogg`` - it becomes a
            file on the server. Nothing there may carry it yet, not even a texture of
            the game's.
        :param player: Send it to this player alone. The server forgets the file again
            once it has arrived, so use this for anything that changes.
        :param keep: Write it into Luanti's own data directory, so it is still there
            after a server restart. Everything else is gone when the server stops.
        :param timeout: How many seconds to wait for the file to arrive.
        :return: The name it is usable under.
        :raises TypeError: If ``image`` is a string, or something Miney cannot read.
        :raises ValueError: If the format is not PNG, JPEG or Ogg, or the file is larger
            than :data:`~miney.assets.MAX_UPLOAD`.
        :raises ~miney.exceptions.PlayerOffline: If ``player`` is not in the game.
        :raises ~miney.exceptions.AssetError: If the server refused the picture.
        :raises ~miney.exceptions.AssetTimeout: If it never arrived on the client.
        """
        data, kind = _read(image)

        if len(data) > MAX_UPLOAD:
            raise ValueError(
                f"This file is {len(data)} bytes and Miney sends at most "
                f"{MAX_UPLOAD}. It travels over the same connection as the game, so a "
                f"big one makes the world stutter. Save it smaller and try again."
            )

        if name is None:
            name = f"miney_{hashlib.sha256(data).hexdigest()[:12]}.{kind}"
        elif not _NAME.match(name) or ".." in name:
            raise ValueError(
                f"{name!r} cannot be the name of an asset. With keep=True it becomes "
                f"a file on the server, so it may hold letters, digits, '.', '-' and "
                f"'_' only, and it has to end in .png, .jpg or .ogg."
            )

        player_name = getattr(player, "name", player)
        if player_name is not None and not isinstance(player_name, str):
            raise TypeError(
                f"'player' is a player or a player name, not a "
                f"{type(player).__name__}. Use lt.players.Steve or \"Steve\"."
            )

        options = {}
        if player_name is not None:
            options["player"] = player_name
        if keep:
            options["keep"] = True

        dumps = self.lt.lua.dumps
        answer = self.lt.lua.run(
            f"return miney_assets.put({dumps(name)}, "
            f"{dumps(base64.b64encode(data).decode())}, {dumps(options)})"
        )
        if isinstance(answer, dict) and "error" in answer:
            raise _ERROR_KINDS.get(answer.get("kind"), AssetError)(answer["error"])

        self._wait_for(name, player_name, len(data), timeout)
        logger.debug("Uploaded %s (%d bytes)", name, len(data))
        return name

    def _wait_for(self, name: str, player_name: str | None, size: int,
                  timeout: float) -> None:
        """
        Block until the client has the file.

        Without this the next line would name a texture the client does not have yet,
        and draw nothing at all - with no error to catch and nothing to search for. A
        sound does the same, and even more quietly.

        :param name: The name it went up under.
        :param player_name: Whose client to wait for, or None for everybody who was
            online when the upload started.
        :param size: How many bytes are on their way, for the error message.
        :param timeout: How many seconds to wait.
        :raises ~miney.exceptions.AssetTimeout: If it never arrived.
        """
        dumps = self.lt.lua.dumps
        code = f"return miney_assets.ready({dumps(name)}, {dumps(player_name)})"
        deadline = time.time() + timeout
        while True:
            if self.lt.lua.run(code):
                return
            if time.time() >= deadline:
                raise AssetTimeout(
                    f"The file {name!r} did not arrive within {timeout} seconds. It "
                    f"is {size} bytes, and that is nearly always the reason - try a "
                    f"smaller one."
                )
            time.sleep(POLL_INTERVAL)

    def list(self) -> list[str]:
        """
        The names of everything Miney has put on this server.

        What the game itself ships is not in here - that is in :attr:`textures` and
        :attr:`sounds`.

        :Example:

            >>> lt.assets.list()
            ['miney_3f9a1c7b2e04.png']

        :return: The names, kept ones included.
        """
        return self.lt.lua.run("return miney_assets.list()") or []

    def remove(self, name: str) -> None:
        """
        Forget one picture or sound.

        Anything already using it keeps working until the player rejoins - the client
        has its own copy by then. This only stops it being sent again.

        :param name: A name from :meth:`list`.
        """
        self.lt.lua.run(f"return miney_assets.remove({self.lt.lua.dumps(name)})")

    def clear(self) -> None:
        """
        Forget everything Miney put on this server, kept files included.

        The kept ones are deleted from disk, so this is how you empty them out again::

            >>> lt.assets.clear()

        Affects every script using this server, not only yours.
        """
        count = self.lt.lua.run("return miney_assets.clear()")
        logger.info("Removed %s assets from the server.", count)


def _short_name(mod: str, filename: str) -> str:
    """
    The name a texture or a sound is reachable under below its mod.

    ``default/default_dirt.png`` becomes ``dirt``, and the sound ``default_dig_stone``
    becomes ``dig_stone``, because the mod name is already the attribute above it.
    Repeating it is a convention rather than a rule though, so a name that does not
    follow it keeps all of itself.

    :param mod: The mod it came from.
    :param filename: A file name, extension included, or a sound group name.
    :return: The attribute name.
    """
    short = filename.rsplit(".", 1)[0]
    prefix = mod + "_"
    if short.startswith(prefix) and len(short) > len(prefix):
        short = short[len(prefix):]
    return short
