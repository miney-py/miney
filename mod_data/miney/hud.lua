-- The server half of miney/hud.py: what one player sees on top of the world.
--
-- The named registry lives here rather than in Python, for two reasons. A second run
-- of the same script has to replace its own elements instead of stacking duplicates on
-- them, and clear() has to be able to take down what an earlier run left behind - both
-- of which need state that outlives a connection. Generating the names here follows
-- from that: a counter in Python would start at 1 again with every REPL and quietly
-- overwrite whatever another script called text_1.

miney_hud = {}

-- player_name -> name -> {id = <hud id>, kind = "text"}
local elements = {}

-- player_name -> kind -> how many have been named so far
local counters = {}

--- The player, or nil when they are not in the game.
--
-- Everything here answers nil in that case, and Python turns that into PlayerOffline.
-- A HUD is per player and lives in their connection; there is nothing to write to
-- while they are away.
--
-- @param player_name (string)
-- @return (ObjectRef or nil)
local function online(player_name)
    if type(player_name) ~= "string" then return nil end
    return minetest.get_player_by_name(player_name)
end

local function registry(player_name)
    local mine = elements[player_name]
    if not mine then
        mine = {}
        elements[player_name] = mine
    end
    return mine
end

--- The next name of its kind for this player: text_1, text_2, ...
local function invent_name(player_name, kind)
    local mine = counters[player_name]
    if not mine then
        mine = {}
        counters[player_name] = mine
    end
    mine[kind] = (mine[kind] or 0) + 1
    return kind .. "_" .. mine[kind]
end

--- Add an element, or change the one that already has this name.
--
-- @param player_name (string) - Whose screen.
-- @param name (string or nil) - What to file it under; invented when nil.
-- @param kind (string) - The element type, as in Luanti's `type` field.
-- @param def (table) - The element's fields, already in Luanti's own names.
-- @return (table or nil) - {name = ...}, {error = ...}, or nil when offline.
function miney_hud.set(player_name, name, kind, def)
    local player = online(player_name)
    if not player then return nil end

    def = def or {}
    if not name then
        name = invent_name(player_name, kind)
    end

    local mine = registry(player_name)
    local entry = mine[name]

    if entry and entry.kind == kind then
        -- The same thing again: change it in place, which is what keeps a counter
        -- updating without flickering.
        for key, value in pairs(def) do
            player:hud_change(entry.id, key, value)
        end
        return {name = name}
    end

    if entry then
        -- Same name, different kind. Nothing can turn a text into an image, so the
        -- old one goes.
        player:hud_remove(entry.id)
        mine[name] = nil
    end

    -- `type` and not `hud_elem_type`: the latter has been the deprecated spelling
    -- since 5.9, which is the oldest engine Miney talks to.
    def.type = kind
    local id = player:hud_add(def)
    if not id then
        return {error = "The server would not add a '" .. tostring(kind) ..
            "' element. Check its fields against Luanti's HUD documentation."}
    end
    mine[name] = {id = id, kind = kind}
    return {name = name}
end

--- Change fields of an element that is already there.
--
-- @param player_name (string)
-- @param name (string)
-- @param def (table) - The fields to change, in Luanti's own names.
-- @return (table or nil) - {ok = true}, {error = ..., kind = "gone"}, or nil.
function miney_hud.change(player_name, name, def)
    local player = online(player_name)
    if not player then return nil end

    local entry = registry(player_name)[name]
    if not entry then
        return {error = "There is no HUD element called '" .. tostring(name) ..
            "' on this screen.", kind = "gone"}
    end

    for key, value in pairs(def or {}) do
        player:hud_change(entry.id, key, value)
    end
    return {ok = true}
end

--- Take one element off the screen.
--
-- Removing something that is not there is not an error: it is gone either way.
--
-- @param player_name (string)
-- @param name (string)
-- @return (boolean or nil) - True if there was one, nil when offline.
function miney_hud.remove(player_name, name)
    local player = online(player_name)
    if not player then return nil end

    local mine = registry(player_name)
    local entry = mine[name]
    if not entry then return false end
    mine[name] = nil
    player:hud_remove(entry.id)
    return true
end

--- Take everything Miney put on this screen back down.
--
-- @param player_name (string)
-- @return (boolean or nil)
function miney_hud.clear(player_name)
    local player = online(player_name)
    if not player then return nil end

    for name, entry in pairs(registry(player_name)) do
        player:hud_remove(entry.id)
    end
    elements[player_name] = nil
    counters[player_name] = nil
    return true
end

--- What Luanti currently draws by itself.
--
-- @param player_name (string)
-- @return (table or nil) - hotbar, healthbar, crosshair and the rest, as booleans.
function miney_hud.flags(player_name)
    local player = online(player_name)
    if not player then return nil end
    return player:hud_get_flags()
end

--- Switch some of those on or off. A flag not named is left alone.
--
-- @param player_name (string)
-- @param flags (table) - flag name -> boolean.
-- @return (boolean or nil)
function miney_hud.set_flags(player_name, flags)
    local player = online(player_name)
    if not player then return nil end
    player:hud_set_flags(flags or {})
    return true
end

local HOTBAR = {
    slots = {get = "hud_get_hotbar_itemcount", set = "hud_set_hotbar_itemcount"},
    image = {get = "hud_get_hotbar_image", set = "hud_set_hotbar_image"},
    selected_image = {
        get = "hud_get_hotbar_selected_image",
        set = "hud_set_hotbar_selected_image",
    },
}

--- Read or write one of the three things the built-in hotbar has.
--
-- @param player_name (string)
-- @param field (string) - "slots", "image" or "selected_image".
-- @param value (any) - What to set it to, or nil to read it.
-- @return (any or nil) - The value when reading, true when writing.
function miney_hud.hotbar(player_name, field, value)
    local player = online(player_name)
    if not player then return nil end

    local names = HOTBAR[field]
    if not names then return nil end
    if value == nil then
        return player[names.get](player)
    end
    player[names.set](player, value)
    return true
end

-- Their screen goes with them, so nothing here may outlive the connection - the same
-- reason player_scratch is dropped in init.lua.
minetest.register_on_leaveplayer(function(player)
    local name = player:get_player_name()
    elements[name] = nil
    counters[name] = nil
end)

return miney_hud
