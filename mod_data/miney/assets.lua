-- The server half of miney/assets.py: pictures a script sends to a client, and the
-- texture names the game already has. Luanti's own word for all of this is "media".
--
-- A note on two directories with the same name, because they are unrelated:
--
--   * this mod's source lives in the repository's mod_data/ folder;
--   * kept pictures are written to minetest.get_mod_data_path(), which is Luanti's
--     own <path_user>/mod_data/miney.
--
-- The second one is the only directory a mod may write to that also survives a
-- restart. Everything the server really scans for media at startup - worldmods/, the
-- mod and game directories, <path_user>/textures/server - is either read-only for a
-- mod or not scanned at all. That is why keep = true re-announces its files here at
-- every mod load instead of simply dropping them somewhere the engine looks.

miney_assets = {}

-- Everything Miney has kept on disk, added up. Refused above this, because a loop
-- with keep = true writes a file every time round. Mirrors the number named in
-- miney/assets.py's docstrings.
local MAX_KEPT = 256 * 1024 * 1024

-- get_mod_data_path() must be called while mods load; later it returns nil.
local ASSET_DIR = minetest.get_mod_data_path() .. "/assets"

-- name -> {keep = bool, ephemeral = bool, size = number}
-- What the server currently knows under that name. Luanti refuses to learn a name
-- twice, so this is also what makes a repeated upload free instead of an error.
local media = {}

-- name -> {expect = {player_name = true}, got = {player_name = true}}
-- Who the picture is on its way to, and who already has it. Kept apart from `media`
-- because an ephemeral entry disappears from the server the moment it is delivered,
-- while Python still has to be able to ask whether that happened.
local pending = {}

local kept_bytes = 0

local ALLOWED_SUFFIX = {png = true, jpg = true, jpeg = true}

--- Refuse a name that must not become a file name.
--
-- The name reaches here from a script, and with keep = true it becomes a path. So it
-- may carry nothing but letters, digits, dot, dash and underscore, and no "..".
--
-- @param name (any) - What the caller passed.
-- @return (string or nil) - What is wrong with it, or nil if nothing is.
local function bad_name(name)
    if type(name) ~= "string" or name == "" then
        return "An asset name has to be a string."
    end
    if #name > 128 then
        return "The name '" .. string.sub(name, 1, 32) .. "...' is too long."
    end
    if not string.match(name, "^[%w_%-%.]+$") or string.find(name, "%.%.") then
        return "The name '" .. name .. "' may only contain letters, digits, '.', " ..
            "'-' and '_', and no '..'."
    end
    local suffix = string.match(name, "%.(%a+)$")
    if not suffix or not ALLOWED_SUFFIX[string.lower(suffix)] then
        return "The name '" .. name .. "' has to end in .png or .jpg."
    end
    return nil
end

--- Put a picture on the server.
--
-- @param name (string) - What it will be usable as.
-- @param data_b64 (string) - The file, base64 encoded.
-- @param opts (table) - {player = <name or nil>, keep = <bool or nil>}
-- @return (table) - {name = ...}, or {error = ..., kind = "limit"/"offline"/nil}.
function miney_assets.put(name, data_b64, opts)
    opts = opts or {}

    local wrong = bad_name(name)
    if wrong then
        return {error = wrong}
    end

    -- Already here: answer as delivered rather than asking the engine to learn a name
    -- it refuses to learn twice. The picture is the same one, because the name Miney
    -- generates is a hash of it.
    if media[name] then
        return {name = name}
    end

    local data = minetest.decode_base64(data_b64)
    if not data then
        return {error = "The picture '" .. name .. "' did not survive the trip here."}
    end

    -- Who has to confirm before Python's upload() may return. A player who joins
    -- while it is on its way is not waited for, and does not need to be.
    local expect = {}
    if opts.player then
        if not minetest.get_player_by_name(opts.player) then
            return {
                error = "'" .. tostring(opts.player) .. "' is not in the game, so " ..
                    "there is nobody to send the picture to.",
                kind = "offline",
            }
        end
        expect[opts.player] = true
    else
        for _, player in ipairs(minetest.get_connected_players()) do
            expect[player:get_player_name()] = true
        end
    end

    local options = {filename = name}
    if opts.keep then
        if kept_bytes + #data > MAX_KEPT then
            return {
                error = "The kept pictures on this server come to " .. kept_bytes ..
                    " bytes and at most " .. MAX_KEPT .. " are allowed. Use " ..
                    "lt.assets.clear() to empty them out.",
                kind = "limit",
            }
        end
        minetest.mkdir(ASSET_DIR)
        local path = ASSET_DIR .. "/" .. name
        if not minetest.safe_file_write(path, data) then
            return {error = "Could not write the picture to " .. path .. "."}
        end
        kept_bytes = kept_bytes + #data
        options.filepath = path
    else
        options.filedata = data
        -- Only a picture meant for one player is ephemeral: the server hands it over
        -- and forgets it again, which is what keeps a chart redrawn every few seconds
        -- from filling anything up. Without a player it has to stay in the media list
        -- so that somebody joining later still gets it.
        options.to_player = opts.player
        options.ephemeral = opts.player ~= nil
    end

    -- Both tables are filled before the call: the callback may fire from inside it.
    media[name] = {
        keep = opts.keep and true or false,
        ephemeral = options.ephemeral or false,
        size = #data,
    }
    pending[name] = {expect = expect, got = {}}

    local accepted = minetest.dynamic_add_media(options, function(player_name)
        local entry = pending[name]
        if entry then
            entry.got[player_name] = true
        end
        -- The server erases an ephemeral entry from its own media list once it has
        -- been delivered, so a record claiming otherwise would answer "already here"
        -- for a name that is gone.
        if media[name] and media[name].ephemeral then
            media[name] = nil
        end
    end)

    if not accepted then
        media[name] = nil
        pending[name] = nil
        return {error = "The server refused the picture '" .. name .. "'. Its log " ..
            "says why; the usual reason is a name something else already carries."}
    end

    return {name = name}
end

--- Has the picture arrived?
--
-- @param name (string) - The name it went up under.
-- @param player_name (string or nil) - Whose client to ask about. Without one, every
--        player who was in the game when the upload started.
-- @return (boolean)
function miney_assets.ready(name, player_name)
    local entry = pending[name]
    if not entry then
        return false
    end
    if player_name then
        return entry.got[player_name] == true
    end
    for who in pairs(entry.expect) do
        if not entry.got[who] then
            return false
        end
    end
    return true
end

--- Everything Miney has put on this server.
--
-- @return (table) - The names, sorted.
function miney_assets.list()
    local names = {}
    for name in pairs(media) do
        names[#names + 1] = name
    end
    table.sort(names)
    return names
end

--- Forget one picture, and delete it from disk if it was kept.
--
-- @param name (string) - A name from list().
-- @return (boolean) - True if there was one.
function miney_assets.remove(name)
    local entry = media[name]
    media[name] = nil
    pending[name] = nil
    if entry and entry.keep then
        os.remove(ASSET_DIR .. "/" .. name)
        kept_bytes = math.max(0, kept_bytes - (entry.size or 0))
    end
    return entry ~= nil
end

--- Forget everything Miney has put here, kept pictures included.
--
-- @return (number) - How many were removed.
function miney_assets.clear()
    local count = 0
    for _, name in ipairs(miney_assets.list()) do
        if miney_assets.remove(name) then
            count = count + 1
        end
    end
    return count
end

--- Everything below one directory, subdirectories included.
--
-- The engine flattens a media directory tree into one namespace (fillMediaCache in
-- server.cpp), so a mod that sorts its textures into folders is no different from one
-- that does not.
--
-- @param dir (string) - Where to start.
-- @param into (table) - Collects the file names.
local function collect(dir, into)
    for _, name in ipairs(minetest.get_dir_list(dir, false) or {}) do
        into[#into + 1] = name
    end
    for _, sub in ipairs(minetest.get_dir_list(dir, true) or {}) do
        collect(dir .. "/" .. sub, into)
    end
end

--- Which mod a loose texture file belongs to, going by its name.
--
-- Only used where there is nothing better to go on: a game keeps its textures in one
-- directory of its own, so the file is all there is. Longest match wins and it is
-- matched against the real mod list rather than split on the first underscore -
-- "mcl_core_stone.png" belongs to "mcl_core", not to "mcl".
--
-- @param filename (string) - The file's name, extension included.
-- @param is_mod (table) - modname -> true.
-- @return (string or nil) - The mod's name, or nil if no mod claims it.
local function owner(filename, is_mod)
    local base = string.match(filename, "^(.*)%.[^.]+$") or filename
    while base do
        if is_mod[base] then
            return base
        end
        base = string.match(base, "^(.*)_[^_]*$")
    end
    return nil
end

--- Every texture the server can draw with, grouped by the mod it belongs to.
--
-- Two places carry them, both of which the engine reads at startup: each mod's own
-- textures/ directory, and the game's single textures/ directory. VoxeLibre uses the
-- second one for nearly everything, so a scan of mod directories alone finds almost
-- nothing on Miney's default game.
--
-- Not covered: <path_user>/textures/server, which the engine reads as well. There is
-- no way to ask Lua where that is, and a server texture pack replaces names that are
-- in here anyway.
--
-- @return (table) - modname -> {file names}
function miney_assets.textures()
    local out = {}
    local is_mod = {}
    for _, mod in ipairs(minetest.get_modnames()) do
        is_mod[mod] = true
    end

    for mod in pairs(is_mod) do
        local dir = minetest.get_modpath(mod) .. "/textures"
        if minetest.path_exists(dir) then
            local files = {}
            collect(dir, files)
            if #files > 0 then
                out[mod] = files
            end
        end
    end

    local game = minetest.get_game_info()
    local game_dir = game.path .. "/textures"
    if minetest.path_exists(game_dir) then
        local files = {}
        collect(game_dir, files)
        for _, name in ipairs(files) do
            local mod = owner(name, is_mod) or game.id
            out[mod] = out[mod] or {}
            table.insert(out[mod], name)
        end
    end

    return out
end

-- A player who left cannot confirm anything any more, so an upload still waiting for
-- them would wait until it times out.
minetest.register_on_leaveplayer(function(player)
    local name = player:get_player_name()
    for _, entry in pairs(pending) do
        entry.expect[name] = nil
        entry.got[name] = nil
    end
end)

-- What makes keep = true work at all: dynamic_add_media may be called while mods load
-- as long as the callback is nil (5.9+), so everything written here in an earlier run
-- is announced again. Nothing is waited for - these go out with the media every client
-- receives when it joins.
minetest.mkdir(ASSET_DIR)
for _, name in ipairs(minetest.get_dir_list(ASSET_DIR, false) or {}) do
    local path = ASSET_DIR .. "/" .. name
    local size = 0
    local file = io.open(path, "rb")
    if file then
        size = file:seek("end")
        file:close()
    end
    kept_bytes = kept_bytes + size
    media[name] = {keep = true, ephemeral = false, size = size}
    pending[name] = {expect = {}, got = {}}
    minetest.dynamic_add_media({filepath = path, filename = name})
end

return miney_assets
