"""
The screen: text, markers, images and bars that stay where you put them.
"""
import logging
import re
from typing import TYPE_CHECKING, Any

from .exceptions import HudElementGone, PlayerOffline

if TYPE_CHECKING:
    from .luanti import Luanti
    from .player import Player


logger = logging.getLogger(__name__)

#: Where an element can go without doing arithmetic. The numbers are shares of the
#: screen, which is what Luanti wants; the middle of the screen is ``(0.5, 0.5)``.
POSITIONS = {
    "top left": (0.0, 0.0),
    "top": (0.5, 0.0),
    "top right": (1.0, 0.0),
    "left": (0.0, 0.5),
    "center": (0.5, 0.5),
    "right": (1.0, 0.5),
    "bottom left": (0.0, 1.0),
    "bottom": (0.5, 1.0),
    "bottom right": (1.0, 1.0),
}

#: What Luanti draws on its own, and can be told not to. Read and written together
#: through ``hud_get_flags``/``hud_set_flags``.
FLAGS = (
    "hotbar", "healthbar", "breathbar", "crosshair", "wielditem", "minimap",
    "minimap_radar", "basic_debug", "chat",
)

#: Miney's name for a field, and the name Luanti wants for it. Luanti reuses ``text``
#: and ``number`` for something different in every element type, which is exactly the
#: kind of thing nobody should have to learn to put a word on a screen.
_FIELDS = {
    "color": "number",
    "texture": "text",
    "value": "number",
    "max_value": "item",
    "label": "name",
    "world_position": "world_pos",
    "list_name": "text",
    "slots": "number",
    "selected": "item",
}

#: Fields that are a pair of numbers on the way to Luanti, whatever they arrive as.
_XY_FIELDS = ("scale", "offset", "size", "alignment")

#: What ``bold``, ``italic`` and ``mono`` add up to in Luanti's ``style`` bit field.
_STYLE_BITS = {"bold": 1, "italic": 2, "mono": 4}

_HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _color(value: Any) -> int:
    """
    :param value: ``"#rrggbb"`` or an integer.
    :return: What Luanti wants in its ``number`` field.
    :raises ValueError: For anything else.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and _HEX_COLOR.match(value):
        return int(value[1:], 16)
    raise ValueError(
        f"{value!r} is not a colour. Write it as \"#rrggbb\", for example "
        f'"#ffcc00" for gold, or give the number directly (0xffcc00).'
    )


def _xy(value: Any) -> dict:
    """
    :param value: One number for both axes, a ``(x, y)`` pair, or a dict of them.
    :return: ``{"x": ..., "y": ...}``, which is what every Luanti field of this kind
        expects.
    :raises ValueError: If it is neither.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, (int, float)):
        return {"x": value, "y": value}
    try:
        x, y = value
    except (TypeError, ValueError):
        raise ValueError(
            f"{value!r} needs to be one number for both directions, or two of them "
            f"as in (4, 2)."
        ) from None
    return {"x": x, "y": y}


def _position(value: Any) -> tuple[dict, dict]:
    """
    Turn a place on the screen into the two fields Luanti needs for it.

    Luanti draws an element *from* its position outwards, so a position alone puts
    anything in a corner half off the screen. The alignment that keeps it on comes
    from the position itself: ``1 - 2 * share``, which is ``1`` at the left edge,
    ``0`` in the middle and ``-1`` at the right one.

    :param value: One of :data:`POSITIONS`, or a ``(x, y)`` pair of shares in 0..1.
    :return: The ``position`` and the ``alignment`` field.
    :raises ValueError: If the name is not one of the nine.
    """
    if isinstance(value, str):
        if value not in POSITIONS:
            raise ValueError(
                f"{value!r} is not a place on the screen. Use one of "
                f"{', '.join(repr(name) for name in POSITIONS)}, or a pair like "
                f"(0.25, 0.75) for anywhere else."
            )
        x, y = POSITIONS[value]
    else:
        pair = _xy(value)
        x, y = float(pair["x"]), float(pair["y"])
    return {"x": x, "y": y}, {"x": 1 - 2 * x, "y": 1 - 2 * y}


class HudElement:
    """
    One thing on one player's screen, and the handle that changes it.

    You do not create this class yourself, it comes back from
    :meth:`Hud.add` and the methods next to it::

        >>> score = lt.players.Steve.hud.text("Score: 0", position="top left")
        >>> score.text = "Score: 7"
        >>> score.color = "#ffcc00"
        >>> score.remove()

    Reading a field gives back what Miney last set, without asking the server: Luanti
    offers no way to read a HUD element back. So a field nobody has set reads as
    ``None`` even though the screen shows Luanti's default.

    .. important::

       The element belongs to that one player and stays on their screen until
       something takes it down - long after the script that made it has ended. It does
       not survive them leaving the game, though: a player who comes back comes back to
       an empty screen.
    """

    def __init__(self, hud: "Hud", name: str, kind: str, fields: dict):
        """
        :param hud: The :class:`Hud` this element lives on.
        :param name: The name the mod filed it under.
        :param kind: The element type, ``"text"``, ``"waypoint"`` and so on.
        :param fields: What it was created with, remembered for reading back.
        """
        self._hud = hud
        #: The name the mod filed this element under. Passing it to
        #: :meth:`Hud.add` again changes this element instead of adding another.
        self.name = name
        #: Which kind of element this is - ``"text"``, ``"image"``, ``"statbar"`` ...
        self.kind = kind
        self._fields = dict(fields)

    def __repr__(self) -> str:
        return f'<HudElement "{self.name}" ({self.kind}) for "{self._hud.player.name}">'

    def remove(self) -> None:
        """
        Take this element off the player's screen.

        Doing it twice is not an error, and neither is doing it to an element the
        player already lost by leaving - it is gone either way, which is the point.
        """
        self._hud._run(
            f"return miney_hud.remove({self._hud._who}, "
            f"{self._hud.lt.lua.dumps(self.name)})"
        )

    def _set(self, field: str, value: Any) -> None:
        """
        :param field: Miney's name for the field.
        :param value: What to set it to.
        :raises miney.exceptions.HudElementGone: If the element is not there anymore.
        """
        self._fields[field] = value
        definition = _translate({field: value}, self._fields)
        answer = self._hud._run(
            f"return miney_hud.change({self._hud._who}, "
            f"{self._hud.lt.lua.dumps(self.name)}, "
            f"{self._hud.lt.lua.dumps(definition)})"
        )
        if isinstance(answer, dict) and answer.get("kind") == "gone":
            raise HudElementGone(
                f'This HUD element is gone: "{self.name}" is not on '
                f'"{self._hud.player.name}"\'s screen anymore, so there is nothing to '
                f"change. Create it again."
            )


def _field(name: str, doc: str) -> property:
    """
    One of :class:`HudElement`'s fields, as a property.

    Written once instead of twenty times over: they all read from memory and all write
    the same way, and the only thing that really differs is the sentence explaining
    what the field does.

    :param name: Miney's name for the field.
    :param doc: The docstring the property gets.
    :return: The property.
    """
    return property(
        lambda self: self._fields.get(name),
        lambda self, value: self._set(name, value),
        doc=doc,
    )


HudElement.text = _field(
    "text",
    "The words on a ``text`` element. Setting it to ``\"\"`` hides the element.",
)
HudElement.color = _field(
    "color",
    'The colour of a ``text`` or ``waypoint`` element, as ``"#rrggbb"`` or a number.',
)
HudElement.texture = _field(
    "texture",
    "The picture an ``image``, ``statbar`` or ``compass`` element draws. A texture "
    "name from :attr:`lt.assets.textures <miney.Assets.textures>`, or a name "
    ":meth:`lt.assets.upload() <miney.Assets.upload>` gave back.",
)
HudElement.value = _field(
    "value",
    "How much of a ``statbar`` is filled, counted in **half** pictures - a full row "
    "of ten hearts is ``20``.",
)
HudElement.max_value = _field(
    "max_value",
    "How long a ``statbar`` is in total, counted in half pictures. The empty part is "
    "drawn with the same picture unless ``off_texture`` says otherwise.",
)
HudElement.label = _field("label", "The name a ``waypoint`` shows in the world.")
HudElement.world_position = _field(
    "world_position",
    "Where a ``waypoint`` sits in the world, as a :class:`~miney.Point`.",
)
HudElement.position = _field(
    "position",
    "Where on the screen it sits: one of :data:`~miney.hud.POSITIONS`, or a ``(x, y)`` "
    "pair of "
    "shares between 0 and 1.",
)
HudElement.offset = _field(
    "offset", "A nudge in pixels from :attr:`position`, as ``(x, y)``."
)
HudElement.scale = _field(
    "scale",
    "How big a picture is drawn. ``1`` is its own size, ``4`` is four times that, and "
    "a **negative** number is a share of the screen: ``(-50, -50)`` is half the screen "
    "whatever the resolution.",
)
HudElement.size = _field("size", "A fixed size in pixels, as ``(x, y)``.")
HudElement.alignment = _field(
    "alignment",
    "Which way the element grows from its :attr:`position`, each between ``-1`` and "
    "``1``. Miney sets this from the position, so you rarely need it.",
)
HudElement.z_index = _field(
    "z_index", "What is drawn on top of what. Higher is nearer the front."
)
HudElement.direction = _field(
    "direction",
    "Which way a ``statbar`` or ``inventory`` grows: 0 left to right, 1 right to "
    "left, 2 top to bottom, 3 bottom to top.",
)


def _translate(fields: dict, all_fields: dict = None) -> dict:
    """
    Turn Miney's field names into Luanti's.

    :param fields: What to translate.
    :param all_fields: Every field the element has, needed for the ones that Luanti
        packs together - ``bold``, ``italic`` and ``mono`` are one number over there.
    :return: The Lua table to send.
    :raises ValueError: For a colour, a position or a pair that is not one.
    """
    all_fields = all_fields if all_fields is not None else fields
    out = {}
    for key, value in fields.items():
        if value is None:
            continue
        if key == "position":
            out["position"], out["alignment"] = _position(value)
        elif key == "color":
            out["number"] = _color(value)
        elif key in _STYLE_BITS:
            out["style"] = sum(
                bit for field, bit in _STYLE_BITS.items() if all_fields.get(field)
            )
        elif key in _XY_FIELDS:
            out[key] = _xy(value)
        elif key == "world_position":
            out["world_pos"] = dict(value)
        else:
            out[_FIELDS.get(key, key)] = value

    # Luanti puts the length of a statbar in "item" and draws its empty part with
    # "text2" - and without text2 the length does nothing at all. Nobody would guess
    # that, so max_value brings the picture along.
    if "item" in out and "text2" not in out and "text" in out:
        out["text2"] = out["text"]
    return out


class Hud:
    """
    What one player sees on their screen, on top of the world.

    :meth:`~miney.Chat.send_to_player` scrolls away; this stays. It is reached through
    :attr:`Player.hud <miney.Player.hud>` and never created directly::

        >>> p = lt.players.Steve
        >>> p.hud.text("Welcome!")
        <HudElement "text_1" (text) for "Steve">

    Every element type has a method of its own - :meth:`text`, :meth:`waypoint`,
    :meth:`image`, :meth:`image_waypoint`, :meth:`statbar`, :meth:`inventory` and
    :meth:`compass` - and all of them are one line around :meth:`add`.

    What Luanti draws by itself is here too, as plain properties::

        >>> p.hud.healthbar = False
        >>> p.hud.crosshair = False
        >>> p.hud.hotbar_slots = 8

    .. important::

       An element stays up until something takes it down, long after your script has
       ended - :meth:`clear` is the broom. Nothing survives the player leaving the
       game, though. And giving an element a ``name`` replaces the one that had it,
       while leaving the name out stacks a new one on top: run a nameless script twice
       and there are two texts sitting on each other.
    """

    def __init__(self, luanti: "Luanti", player: "Player"):
        """
        :param luanti: The parent :class:`~miney.Luanti` object.
        :param player: Whose screen this is.
        """
        self.lt = luanti
        #: Whose screen this is.
        self.player = player

    def __repr__(self) -> str:
        return f'<Luanti Hud for "{self.player.name}">'

    @property
    def _who(self) -> str:
        """
        :return: The player's name, as a Lua string literal.
        """
        return self.lt.lua.dumps(self.player.name)

    def _run(self, code: str) -> Any:
        """
        Ask the mod something, and turn "no such player" into a sentence.

        :param code: The Lua to run.
        :return: Whatever the mod answered.
        :raises miney.exceptions.PlayerOffline: If the player is not in the game.
        """
        answer = self.lt.lua.run(code)
        if answer is None:
            raise PlayerOffline(
                f"{self.player.name!r} is not in the game, so there is no screen to "
                f"draw on."
            )
        return answer

    def add(self, kind: str, name: str = None, **fields) -> HudElement:
        """
        Put an element on the player's screen.

        This is the one that can do everything; :meth:`text`, :meth:`image` and the
        others are a line each around it, and easier to find. Use this one for the
        element types that have no method of their own - ``"minimap"``, and
        ``"hotbar"`` on a new enough server:

        1. The plain case::

            >>> p.hud.add("text", text="Welcome!")

        2. Named, so that running the script again replaces it instead of stacking a
           second one on top::

            >>> score = p.hud.add("text", name="score", text="Score: 0",
            ...                   position="top left", color="#ffcc00")
            >>> score.text = "Score: 7"

        3. A minimap in the bottom right corner::

            >>> p.hud.add("minimap", position="bottom right", size=(-25, -25))

        The fields are Miney's names, not Luanti's: ``color``, ``texture``, ``value``,
        ``max_value``, ``label``, ``world_position``, ``list_name``, ``slots`` and
        ``selected`` are translated on the way, and ``position``, ``offset``,
        ``scale``, ``size``, ``alignment``, ``z_index`` and ``direction`` go through
        unchanged. Which of them an element type reads is in
        `Luanti's HUD documentation <https://api.luanti.org/hud/>`_ - anything a type
        does not read is quietly ignored by the engine.

        :param kind: The element type: ``"text"``, ``"image"``, ``"statbar"``,
            ``"waypoint"``, ``"image_waypoint"``, ``"inventory"``, ``"compass"`` or
            ``"minimap"``.
        :param name: A name to find it under later. Using one twice changes the first
            element instead of adding a second. Without one, the server invents a name
            and every call adds another element.
        :param fields: The element's fields, see above.
        :return: The handle, for changing it later.
        :raises ValueError: For a colour, position or pair Miney cannot read.
        :raises ~miney.exceptions.PlayerOffline: If the player is not in the game.
        """
        if kind.endswith("waypoint") and fields.get("position") is not None:
            raise ValueError(
                f"A {kind} is placed by its world_position, not by a position on the "
                f"screen. Pass one of them, not both."
            )
        if not kind.endswith("waypoint") and kind != "hotbar":
            fields.setdefault("position", "center")

        answer = self._run(
            f"return miney_hud.set({self._who}, {self.lt.lua.dumps(name)}, "
            f"{self.lt.lua.dumps(kind)}, {self.lt.lua.dumps(_translate(fields))})"
        )
        if isinstance(answer, dict) and "error" in answer:
            raise ValueError(answer["error"])
        return HudElement(self, answer["name"], kind, fields)

    def _picture(self, texture: Any) -> str:
        """
        :param texture: A texture name the server already has, or anything
            :meth:`~miney.Assets.upload` can read.
        :return: A name the server has.
        """
        if isinstance(texture, str):
            return texture
        return self.lt.assets.upload(texture)

    def text(self, text: str, **fields) -> HudElement:
        """
        Write something on the player's screen and leave it there.

        The same as ``hud.add("text", text=text, ...)``::

            >>> p.hud.text("Welcome!")
            >>> score = p.hud.text("Score: 0", position="top left", name="score")
            >>> score.text = "Score: 7"

        :param text: What it says.
        :param fields: ``color``, ``position``, ``offset``, ``size``, ``z_index``,
            ``bold``, ``italic``, ``mono``, and ``name`` - see :meth:`add`.
        :return: The handle, for changing the words later.
        """
        return self.add("text", text=text, **fields)

    def waypoint(self, world_position, label: str = "", **fields) -> HudElement:
        """
        Mark a place in the world, visible through walls and with its distance.

        The same as ``hud.add("waypoint", world_position=..., label=...)``::

            >>> p.hud.waypoint(Point(10, 20, 30), "Base", color="#00ff00")

        A waypoint has no ``position``: it is where the world is, not where the screen
        is. Passing one raises a :class:`ValueError`.

        :param world_position: The :class:`~miney.Point` to mark.
        :param label: The name shown next to it.
        :param fields: ``color``, ``precision``, ``offset``, ``z_index``, and ``name``
            - see :meth:`add`.
        :return: The handle.
        """
        return self.add(
            "waypoint", world_position=world_position, label=label, **fields
        )

    def image(self, texture, **fields) -> HudElement:
        """
        Show a picture on the player's screen.

        The same as ``hud.add("image", texture=...)``::

            >>> p.hud.image(lt.assets.textures.default.mese_crystal, scale=4)
            >>> p.hud.image(Path("cat.png"), position="top right")
            >>> p.hud.image(figure, scale=(-50, -50))     # half the screen

        A :class:`str` is the name of a picture the server already has. Anything else -
        a :class:`~pathlib.Path`, a Pillow image, a matplotlib figure - goes through
        :meth:`lt.assets.upload() <miney.Assets.upload>` first.

        .. note::

           A **negative** ``scale`` is a share of the screen instead of a multiple of
           the picture's own size, so ``scale=(-50, -50)`` fills half the screen on
           every resolution. That is usually what you want for a picture you generated.

        :param texture: A texture name, or a picture to upload.
        :param fields: ``position``, ``offset``, ``scale``, ``alignment``, ``z_index``,
            and ``name`` - see :meth:`add`.
        :return: The handle.
        """
        return self.add("image", texture=self._picture(texture), **fields)

    def image_waypoint(self, texture, world_position, **fields) -> HudElement:
        """
        Show a picture floating at a place in the world.

        The same as ``hud.add("image_waypoint", texture=..., world_position=...)``::

            >>> p.hud.image_waypoint("default_apple.png", Point(10, 20, 30))

        :param texture: A texture name, or a picture to upload.
        :param world_position: The :class:`~miney.Point` to put it at.
        :param fields: ``scale``, ``offset``, ``alignment``, ``z_index``, and ``name``
            - see :meth:`add`.
        :return: The handle.
        """
        return self.add(
            "image_waypoint", texture=self._picture(texture),
            world_position=world_position, **fields,
        )

    def statbar(self, texture, value: int, max_value: int = None,
                off_texture: str = None, **fields) -> HudElement:
        """
        Draw a row of pictures, the way the health bar is drawn.

        The same as ``hud.add("statbar", texture=..., value=...)``::

            >>> hearts = p.hud.statbar("heart.png", value=10, max_value=20)
            >>> hearts.value = 6

        .. important::

           The numbers count **half** pictures, because that is how Luanti draws a half
           heart. Ten whole hearts is ``value=20``.

        :param texture: The picture for the filled part: a texture name, or a picture
            to upload.
        :param value: How many halves are filled.
        :param max_value: How many halves there are in total. The rest is drawn with
            ``off_texture``.
        :param off_texture: The picture for the empty part. Defaults to ``texture``,
            which is what makes ``max_value`` visible at all.
        :param fields: ``position``, ``offset``, ``size``, ``direction``, ``z_index``,
            and ``name`` - see :meth:`add`.
        :return: The handle.
        """
        if off_texture is not None:
            fields["text2"] = self._picture(off_texture)
        return self.add(
            "statbar", texture=self._picture(texture), value=value,
            max_value=max_value, **fields,
        )

    def inventory(self, list_name: str = "main", slots: int = 8,
                  **fields) -> HudElement:
        """
        Show part of the player's inventory on their screen.

        The same as ``hud.add("inventory", list_name=..., slots=...)``::

            >>> p.hud.inventory("main", slots=8, position="bottom")

        :param list_name: Which inventory list to show, usually ``"main"``.
        :param slots: How many item slots of it.
        :param fields: ``selected``, ``position``, ``offset``, ``direction``,
            ``alignment``, ``z_index``, and ``name`` - see :meth:`add`.
        :return: The handle.
        """
        return self.add("inventory", list_name=list_name, slots=slots, **fields)

    def compass(self, texture, **fields) -> HudElement:
        """
        Show a picture that turns with the player.

        The same as ``hud.add("compass", texture=...)``::

            >>> p.hud.compass("compass.png", position="top", size=(128, 32))

        :param texture: A texture name, or a picture to upload.
        :param fields: ``size``, ``scale``, ``direction``, ``position``, ``offset``,
            ``z_index``, and ``name`` - see :meth:`add`.
        :return: The handle.
        """
        return self.add("compass", texture=self._picture(texture), **fields)

    def clear(self) -> None:
        """
        Take everything Miney put on this player's screen back down.

        Elements another script added are taken down too - the mod keeps one registry
        per player, not one per script::

            >>> p.hud.clear()

        What Luanti draws by itself - hearts, crosshair, hotbar - is not affected;
        those are the properties on this class.
        """
        self._run(f"return miney_hud.clear({self._who})")
        logger.debug("Cleared the HUD of %s.", self.player.name)

    def _flag(self, name: str) -> bool:
        """
        :param name: One of :data:`FLAGS`.
        :return: Whether Luanti currently draws it.
        """
        return bool(self._run(f"return miney_hud.flags({self._who})").get(name))

    def _set_flag(self, name: str, value: bool) -> None:
        """
        :param name: One of :data:`FLAGS`.
        :param value: True to draw it, False to hide it.
        :raises TypeError: If ``value`` is not a bool.
        """
        if not isinstance(value, bool):
            raise TypeError(
                f"{name} is either on or off, so it takes True or False, not "
                f"{value!r}."
            )
        self._run(
            f"return miney_hud.set_flags({self._who}, "
            f"{self.lt.lua.dumps({name: value})})"
        )

    def _hotbar(self, field: str, value: Any = None) -> Any:
        """
        :param field: ``"slots"``, ``"image"`` or ``"selected_image"``.
        :param value: What to set it to, or None to read it.
        :return: The current value when reading.
        """
        return self._run(
            f"return miney_hud.hotbar({self._who}, {self.lt.lua.dumps(field)}, "
            f"{self.lt.lua.dumps(value)})"
        )

    @property
    def hotbar_slots(self) -> int:
        """
        How many item slots the hotbar shows, between 1 and 32.

        A player whose ``"main"`` list is shorter than this sees the shorter one -
        Luanti will not invent slots that do not exist::

            >>> p.hud.hotbar_slots = 4

        :return: The number of slots.
        :raises ValueError: If set outside 1..32.
        """
        return self._hotbar("slots")

    @hotbar_slots.setter
    def hotbar_slots(self, value: int) -> None:
        if not isinstance(value, int) or isinstance(value, bool) \
                or not 1 <= value <= 32:
            raise ValueError(
                f"The hotbar holds between 1 and 32 slots, so {value!r} is not a "
                f"number it can take."
            )
        self._hotbar("slots", value)

    @property
    def hotbar_image(self) -> str:
        """
        The picture drawn behind the hotbar::

            >>> p.hud.hotbar_image = "gui_hotbar.png"

        :return: The texture name, empty while the game's own is used.
        """
        return self._hotbar("image")

    @hotbar_image.setter
    def hotbar_image(self, value) -> None:
        self._hotbar("image", self._picture(value))

    @property
    def hotbar_selected_image(self) -> str:
        """
        The picture drawn around the slot the player has selected::

            >>> p.hud.hotbar_selected_image = "gui_hotbar_selected.png"

        :return: The texture name, empty while the game's own is used.
        """
        return self._hotbar("selected_image")

    @hotbar_selected_image.setter
    def hotbar_selected_image(self, value) -> None:
        self._hotbar("selected_image", self._picture(value))


#: A sentence each for the things Luanti draws on its own, so that the generated
#: properties below are documented rather than merely present.
_FLAG_DOCS = {
    "hotbar": "The row of item slots along the bottom of the screen.",
    "healthbar": "The row of hearts.",
    "breathbar": "The row of bubbles that shows up under water.",
    "crosshair": "The little cross in the middle of the screen.",
    "wielditem": "The item in the player's hand, drawn in the corner of the screen.",
    "minimap": "Whether the player is allowed to open the minimap. They can still "
               "choose not to, so switching this on does not put one on the screen.",
    "minimap_radar": "The minimap's radar mode, which sees through the ground. Only "
                     "does anything while :attr:`minimap` is on.",
    "basic_debug": "The debug lines: position, look direction, map seed. A player "
                   "with the ``debug`` privilege sees them regardless.",
    "chat": "Whether chat messages appear on the screen. The chat console still works.",
}

for _name, _doc in _FLAG_DOCS.items():
    setattr(Hud, _name, property(
        lambda self, name=_name: self._flag(name),
        lambda self, value, name=_name: self._set_flag(name, value),
        doc=f"{_doc}\n\n    Switch it off with ``player.hud.{_name} = False``.\n\n"
            f"    :return: Whether Luanti currently draws it.",
    ))
