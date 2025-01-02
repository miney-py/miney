"""
Constants, enumerations and shared data structures for the Luanti client.
"""

class ClientState:
    """Enum-like class for client connection states."""
    DISCONNECTED = 0
    CONNECTING = 1
    AUTHENTICATING = 2
    AUTHENTICATED = 3
    JOINING = 4
    JOINED = 5  # Vollständig verbunden und bereit für Interaktionen


# Protocol commands
class ToServerCommand:
    """Command codes sent from client to server."""
    INIT = 0x02
    INIT2 = 0x11
    CHAT_MESSAGE = 0x32
    CLIENT_READY = 0x43
    FIRST_SRP = 0x50
    SRP_BYTES_A = 0x51
    SRP_BYTES_M = 0x52
    AUTH = 0x39
    INVENTORY_FIELDS = 0x3c
    PLAYERPOS = 0x23
    GOTBLOCKS = 0x24
    DELETEDBLOCKS = 0x25


class ToClientCommand:
    HELLO = 0x02
    AUTH_ACCEPT = 0x03
    ACCESS_DENIED = 0x0A
    BLOCKDATA = 0x20
    ADDNODE = 0x21
    REMOVENODE = 0x22
    INVENTORY = 0x27
    TIME_OF_DAY = 0x29
    CSM_RESTRICTION_FLAGS = 0x2A
    PLAYER_SPEED = 0x2B
    MEDIA_PUSH = 0x2C
    CHAT_MESSAGE = 0x2F
    ACTIVE_OBJECT_REMOVE_ADD = 0x31
    ACTIVE_OBJECT_MESSAGES = 0x32
    HP = 0x33
    MOVE_PLAYER = 0x34
    FOV = 0x36
    DEATHSCREEN = 0x37
    MEDIA = 0x38
    NODEDEF = 0x3A
    ANNOUNCE_MEDIA = 0x3C
    ITEMDEF = 0x3D
    PLAY_SOUND = 0x3F
    STOP_SOUND = 0x40
    PRIVILEGES = 0x41
    INVENTORY_FORMSPEC = 0x42
    DETACHED_INVENTORY = 0x43
    SHOW_FORMSPEC = 0x44
    MOVEMENT = 0x45
    SPAWN_PARTICLE = 0x46
    ADD_PARTICLESPAWNER = 0x47
    HUDADD = 0x49
    HUDRM = 0x4A
    HUDCHANGE = 0x4B
    HUD_SET_FLAGS = 0x4C
    HUD_SET_PARAM = 0x4D
    BREATH = 0x4E
    SET_SKY = 0x4F
    OVERRIDE_DAY_NIGHT_RATIO = 0x50
    LOCAL_PLAYER_ANIMATIONS = 0x51
    EYE_OFFSET = 0x52
    DELETE_PARTICLESPAWNER = 0x53
    CLOUD_PARAMS = 0x54
    FADE_SOUND = 0x55
    UPDATE_PLAYER_LIST = 0x56
    MODCHANNEL_MSG = 0x57
    MODCHANNEL_SIGNAL = 0x58
    NODEMETA_CHANGED = 0x59
    SET_SUN = 0x5A
    SET_MOON = 0x5B
    SET_STARS = 0x5C
    SRP_BYTES_S_B = 0x60
    FORMSPEC_PREPEND = 0x61
    MINIMAP_MODES = 0x62
    SET_LIGHTING = 0x63
    PING = 0xFF
