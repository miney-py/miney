"""
Pictures: the ones the game already has, and the ones you make yourself.
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
_MAGIC = ((b"\x89PNG", "png"), (b"\xff\xd8\xff", "jpg"))

#: The same thing for a :class:`~pathlib.Path`, which is trusted to be named correctly.
_SUFFIXES = {".png": "png", ".jpg": "jpg", ".jpeg": "jpg"}

#: What a ``name=`` of your own may look like. It becomes a file on the server with
#: ``keep=True``, so the mod checks this again - never trust the client with a path.
_NAME = re.compile(r"^[A-Za-z0-9._\-]+\.(?i:png|jpe?g)$")

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
    :return: The file's bytes, and ``"png"`` or ``"jpg"``.
    :raises TypeError: If a :class:`str` was given, which is a name and not a file.
    :raises ValueError: If the format is not one Miney can send.
    """
    if isinstance(image, str):
        raise TypeError(
            f"A string is the name of a picture the server already has, not a file to "
            f'upload. Use Path("{image}") if you meant the file on your computer.'
        )

    if isinstance(image, Path):
        suffix = image.suffix.lower()
        if suffix not in _SUFFIXES:
            raise ValueError(
                f"Miney can upload PNG and JPEG pictures, and {image.name!r} is "
                f"neither. Save it as .png and try again."
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
            f"Miney cannot read a {type(image).__name__} as a picture. Give it bytes, "
            f"a Path, an open file, a Pillow image or a matplotlib figure."
        )

    for magic, kind in _MAGIC:
        if data.startswith(magic):
            return data, kind
    raise ValueError(
        "Miney can upload PNG and JPEG pictures, and this is neither - its first "
        "bytes match no format Miney knows."
    )


class Assets:
    """
    Pictures: what the game already has, and what you make yourself.

    Luanti calls all of this **media**, which is the word to search for in its own
    documentation and on the forums.

    You do not create this class yourself, it is reached through
    :attr:`~miney.Luanti.assets`.

    **Finding a picture the game ships.** Every texture name is one TAB away, the same
    way :attr:`lt.nodes.names <miney.Nodes.names>` works for blocks::

        >>> lt.assets.textures.default.dirt
        'default_dirt.png'

    **Getting your own picture in.** Anything Python can draw goes into the world::

        >>> from pathlib import Path
        >>> name = lt.assets.upload(Path("cat.png"))
        >>> lt.players.Steve.hud.image(name)

    .. important::

       The picture is gone when the server stops, unless you pass ``keep=True``. And it
       travels over the same connection as the game, so a big one is felt as a stutter
       by whoever receives it.
    """

    def __init__(self, luanti: "Luanti"):
        """
        :param luanti: The parent :class:`~miney.Luanti` object.
        """
        self.lt = luanti
        self._textures: NameIterable | None = None
        #: Every texture name, flat. Filled with :attr:`textures`, which is what
        #: ``NameIterable`` iterates over.
        self._names_cache: list[str] = []

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
            if not isinstance(by_mod, dict):
                by_mod = {}
            root = NameIterable(self)
            for mod, files in sorted(by_mod.items()):
                group = NameIterable(self)
                for filename in files:
                    self._names_cache.append(filename)
                    setattr(group, _short_name(mod, filename), filename)
                setattr(root, mod, group)
            self._textures = root
        return self._textures

    def upload(self, image: Any, name: str = None,
               player: "Player | str" = None, keep: bool = False,
               timeout: float = 30) -> str:
        """
        Put a picture on the server and give back the name it is usable under.

        That name goes anywhere a texture name goes - a HUD image, a statbar, a node's
        texture:

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

        3. For one player only, and forgotten again once they have it. This is the one
           to use for a picture that changes, because nothing piles up::

            >>> lt.assets.upload(chart, player=lt.players.Steve)

        4. Still there after the server restarts::

            >>> lt.assets.upload(logo, keep=True)

        .. important::

           **The name is a hash of the picture**, so uploading the same one twice costs
           nothing - and a *changed* picture gets a *different* name. That is not a
           quirk: Luanti refuses to know the same name twice, so a chart that updates
           cannot keep its old name. Whatever shows the picture has to be told the new
           one.

        This call comes back only once the picture has really arrived on the client, so
        the next line can use the name straight away. A 800x600 chart is 40-80 KB and
        arrives without anybody noticing.

        :param image: The picture: :class:`bytes`, a :class:`~pathlib.Path`, an open
            file, a Pillow image or a matplotlib figure. A :class:`str` is *not* a
            picture, it is the name of one the server already has.
        :param name: A name of your own instead of the hash. Letters, digits, ``.``,
            ``-`` and ``_``, ending in ``.png`` or ``.jpg`` - it becomes a file on the
            server. Nothing there may carry it yet, not even a texture of the game's.
        :param player: Send it to this player alone. The server forgets the picture
            again once it has arrived, so use this for anything that changes.
        :param keep: Write it into Luanti's own data directory, so it is still there
            after a server restart. Everything else is gone when the server stops.
        :param timeout: How many seconds to wait for the picture to arrive.
        :return: The name the picture is usable under.
        :raises TypeError: If ``image`` is a string, or something Miney cannot read.
        :raises ValueError: If the format is not PNG or JPEG, or the picture is larger
            than :data:`~miney.assets.MAX_UPLOAD`.
        :raises ~miney.exceptions.PlayerOffline: If ``player`` is not in the game.
        :raises ~miney.exceptions.AssetError: If the server refused the picture.
        :raises ~miney.exceptions.AssetTimeout: If it never arrived on the client.
        """
        data, kind = _read(image)

        if len(data) > MAX_UPLOAD:
            raise ValueError(
                f"This picture is {len(data)} bytes and Miney sends at most "
                f"{MAX_UPLOAD}. It travels over the same connection as the game, so a "
                f"big one makes the world stutter. Save it smaller and try again."
            )

        if name is None:
            name = f"miney_{hashlib.sha256(data).hexdigest()[:12]}.{kind}"
        elif not _NAME.match(name) or ".." in name:
            raise ValueError(
                f"{name!r} cannot be the name of a picture. With keep=True it becomes "
                f"a file on the server, so it may hold letters, digits, '.', '-' and "
                f"'_' only, and it has to end in .png or .jpg."
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
        Block until the client has the picture.

        Without this the next line would name a texture the client does not have yet,
        and draw nothing at all - with no error to catch and nothing to search for.

        :param name: The name the picture went up under.
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
                    f"The picture {name!r} did not arrive within {timeout} seconds. It "
                    f"is {size} bytes, and that is nearly always the reason - try a "
                    f"smaller one."
                )
            time.sleep(POLL_INTERVAL)

    def list(self) -> list[str]:
        """
        The names of everything Miney has put on this server.

        Textures the game itself ships are not in here - those are in
        :attr:`textures`.

        :Example:

            >>> lt.assets.list()
            ['miney_3f9a1c7b2e04.png']

        :return: The names, kept ones included.
        """
        return self.lt.lua.run("return miney_assets.list()") or []

    def remove(self, name: str) -> None:
        """
        Forget one picture.

        Anything already showing it keeps showing it until the player rejoins - the
        client has its own copy by then. This only stops it being sent again.

        :param name: A name from :meth:`list`.
        """
        self.lt.lua.run(f"return miney_assets.remove({self.lt.lua.dumps(name)})")

    def clear(self) -> None:
        """
        Forget everything Miney put on this server, kept pictures included.

        The kept ones are deleted from disk, so this is how you empty them out again::

            >>> lt.assets.clear()

        Affects every script using this server, not only yours.
        """
        count = self.lt.lua.run("return miney_assets.clear()")
        logger.info("Removed %s assets from the server.", count)


def _short_name(mod: str, filename: str) -> str:
    """
    The name a texture is reachable under below its mod.

    ``default/default_dirt.png`` becomes ``dirt``, because the mod name is already the
    attribute above it. Repeating it is a convention rather than a rule though, so a
    file that does not follow it keeps its whole name.

    :param mod: The mod the file came from.
    :param filename: The file's name, extension included.
    :return: The attribute name.
    """
    short = filename.rsplit(".", 1)[0]
    prefix = mod + "_"
    if short.startswith(prefix) and len(short) > len(prefix):
        short = short[len(prefix):]
    return short
