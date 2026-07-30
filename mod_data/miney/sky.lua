-- The server half of miney/sky.py: one player's sky, and how to keep a game from
-- painting over it.
--
-- Setting a sky is one engine call and would need no mod at all - except that a game
-- may own the sky itself. VoxeLibre does: mcl_weather/skycolor.lua rewrites set_sky,
-- set_sun, set_sun, set_stars and override_day_night_ratio for every player about once
-- a second, which is how rain darkens the day and how the Nether glows red. A colour
-- set from Python was gone before the next line of the script ran.
--
-- That game has a chain of filters it builds each sky from, so Miney adds one at the
-- end: what a script has set for a player is laid over what the game just decided, for
-- that player only. Everybody else keeps their weather, and the fields nobody has
-- claimed - fog, the sky colours behind the clouds - stay the game's.

miney_sky = {}

-- player_name -> {sky = {...}, sun = {...}, moon = {...}, stars = {...}, ratio = n}
-- Only the parts a script has actually set are in here; the rest stays the game's.
local held = {}

-- What Python may name, and the engine call that puts it into the world now. Anything
-- not in here is refused rather than stored, so a typo cannot become a sky nobody can
-- reset.
local PARTS = {
    sky = function(player, value) player:set_sky(value) end,
    sun = function(player, value) player:set_sun(value) end,
    moon = function(player, value) player:set_moon(value) end,
    stars = function(player, value) player:set_stars(value) end,
    ratio = function(player, value) player:override_day_night_ratio(value) end,
}

--- A copy of `base` with `over` written on top of it.
--
-- A copy, because the table came out of the game's own filters and may well be one it
-- keeps and hands to the next player too. Writing into it would give everybody the sky
-- of whoever was updated first.
--
-- @param base (table or nil)
-- @param over (table)
-- @return (table)
local function laid_over(base, over)
    local merged = {}
    for k, v in pairs(base or {}) do merged[k] = v end
    for k, v in pairs(over) do merged[k] = v end
    return merged
end

--- Set one part of a player's sky, and hold it there.
--
-- @param player_name (string)
-- @param part (string) one of the keys of PARTS
-- @param value (table or number or nil) what to pass the engine call
-- @return (boolean) true when it was applied, false when the part is not a part
function miney_sky.hold(player_name, part, value)
    local apply = PARTS[part]
    if not apply then return false end

    local mine = held[player_name]
    if not mine then
        mine = {}
        held[player_name] = mine
    end
    -- set_sky{clouds = false} keeps the colour it was not given, and the same is true
    -- of the others, so a part is merged rather than replaced. The ratio is one number
    -- and has nothing to merge.
    if part == "ratio" then
        mine.ratio = value
    else
        mine[part] = laid_over(mine[part], value or {})
    end

    local player = minetest.get_player_by_name(player_name)
    if not player then return false end
    apply(player, value)
    return true
end

--- Give the sky back: forget what was held and put the engine's own values there.
--
-- @param player_name (string)
-- @return (boolean) true when the player was there to reset
function miney_sky.release(player_name)
    held[player_name] = nil

    local player = minetest.get_player_by_name(player_name)
    if not player then return false end
    player:set_sky()
    player:set_sun()
    player:set_moon()
    player:set_stars()
    player:set_clouds()
    player:override_day_night_ratio()

    -- The game paints again by itself within a few seconds; this only saves the wait.
    if mcl_weather and mcl_weather.skycolor
        and mcl_weather.skycolor.update_player_sky_color then
        mcl_weather.skycolor.update_player_sky_color(player)
    end
    return true
end

--- Lay what a script holds over the sky a game just decided on.
--
-- The shape of `sky_data` is VoxeLibre's, from mcl_weather/skycolor.lua: a `sky` table
-- it passes to set_sky, optional `sun`, `moon` and `stars` tables, and a
-- `day_night_ratio`.
--
-- @param player (ObjectRef)
-- @param sky_data (table) modified in place
local function overlay(player, sky_data)
    local mine = held[player:get_player_name()]
    if not mine then return end

    if mine.sky then sky_data.sky = laid_over(sky_data.sky, mine.sky) end
    if mine.sun then sky_data.sun = laid_over(sky_data.sun, mine.sun) end
    if mine.moon then sky_data.moon = laid_over(sky_data.moon, mine.moon) end
    if mine.stars then sky_data.stars = laid_over(sky_data.stars, mine.stars) end
    if mine.ratio ~= nil then sky_data.day_night_ratio = mine.ratio end
end

-- Last in the chain, so this is the one that decides. after_mods, because the mod that
-- owns the chain may well load after this one.
minetest.register_on_mods_loaded(function()
    if mcl_weather and mcl_weather.skycolor and mcl_weather.skycolor.filters then
        table.insert(mcl_weather.skycolor.filters, overlay)
    end
end)

-- The engine drops a player's sky when they leave anyway, so a leftover entry here
-- would only be a sky that comes back on its own the next time they log in.
minetest.register_on_leaveplayer(function(player)
    held[player:get_player_name()] = nil
end)
