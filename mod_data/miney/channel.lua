-- The file channel: how Miney's Python side reaches this mod without being a player.
--
-- Two append-only logs in this mod's own data directory, one JSON record per line.
-- Python appends a request to `c2s`, a globalstep here reads whatever complete lines
-- have appeared since the last one, and answers go out as lines on `s2c`. That is the
-- whole transport: no account, no port, no password, and it works in a singleplayer
-- world started from the Luanti menu, where a second network client is refused outright.
--
-- Three things about it are not obvious and were measured rather than assumed:
--
--   * `io.open` runs the engine's security path check, and on a *read* that resolves
--     builtin, the game directory and every loaded mod path. 2374 microseconds per call
--     on Windows with 34 mods loaded; 214 on Linux. `seek` on a handle that is already
--     open costs 1.9. So both handles are opened once, while mods load, and never
--     again - an idle channel costs one `seek("end")` per step.
--   * `flush()` is not a disk write. It moves bytes out of stdio into the kernel, which
--     is what makes them visible to the other process; the page cache answers Python's
--     read. `core.safe_file_write` would be the obvious call here and is the wrong one:
--     it fsyncs, 4537 microseconds every time.
--   * The newline is the commit marker. A record without its terminator is not a short
--     record, it is not a record at all - the reader leaves its offset where it is and
--     sees the whole line next step. That is what makes a half-written request
--     harmless instead of merely unlikely.
--
-- And the rule that cost a frozen server to find: never re-check the input inside the
-- drain loop. One snapshot per step, process what is in it, return. A loop that looks
-- again keeps finding more, because a client refills faster than a path-checked open
-- drains, and the globalstep never returns.

local modname = minetest.get_current_modname()

miney_channel = {}

-- How long a session may go without saying anything before the mod throws away
-- everything it left behind. Python sends a ping well inside this; the timeout is for
-- the process that was killed rather than the one that said goodbye.
local SESSION_TIMEOUT = 30

-- How much of one server step the pump may spend running requests. A thousand trivial
-- commands cost 3 ms and a thousand node placements do not, so the batch is bounded by
-- the clock and the rest waits for the next step. Lowering it makes a busy Miney script
-- gentler on everyone else in the world.
local STEP_BUDGET_US = tonumber(minetest.settings:get("miney_channel_budget_ms") or "5") * 1000

-- The channel directory, one per world.
--
-- `get_mod_data_path()` is per mod but not per world, and two servers may well be up at
-- once - a project's world and something the user started from the menu. Sharing one
-- `c2s` between them would interleave two request streams into one file. So each world
-- gets its own subdirectory, named after it and stamped with a digest of its full path
-- because two worlds may share a name.
--
-- Both functions only answer while mods load, which is why this runs at dofile time.
local function world_key()
    local path = minetest.get_worldpath()
    local name = string.match(path, "([^/\\]+)[/\\]*$") or "world"
    name = string.gsub(name, "[^%w_%-]", "_")
    local digest
    if minetest.sha1 then
        digest = string.sub(minetest.sha1(path), 1, 8)
    else
        local hash = 5381
        for index = 1, #path do
            hash = (hash * 33 + string.byte(path, index)) % 4294967296
        end
        digest = string.format("%08x", hash)
    end
    return name .. "-" .. digest
end

local base = (minetest.get_mod_data_path and minetest.get_mod_data_path())
    or (minetest.get_worldpath() .. DIR_DELIM .. "miney_channel")
minetest.mkdir(base)

local dir = base .. DIR_DELIM .. world_key()
minetest.mkdir(dir)

local c2s_path = dir .. DIR_DELIM .. "c2s"
local s2c_path = dir .. DIR_DELIM .. "s2c"
local beacon_path = dir .. DIR_DELIM .. "beacon.json"

local requests = nil    -- read handle on c2s, held for the life of the server
local answers = nil     -- append handle on s2c, likewise
local read_off = 0      -- how far into c2s this mod has got
local dirty = false     -- something was written to s2c and not yet flushed

local sessions = {}     -- id -> last time anything arrived from it
local dispatch = nil    -- what init.lua does with a fields table
local forget = nil      -- what init.lua does when a session goes away
local advertised_api = 0 -- the contract version, sent in the beacon and every hello

local function log(level, message)
    minetest.log(level, "[" .. modname .. "/channel] " .. message)
end

--- Send one answer to a session. The only way anything leaves this mod.
--
-- Written straight into the stdio buffer and flushed once at the end of the step, so a
-- batch of a thousand commands costs one flush rather than a thousand.
--
-- Global rather than a field of miney_channel, because every other file in the mod -
-- the Lua result, the callback acknowledgement, the event - reaches for it by name.
--
-- @param who (string) - The session name: "@" and its id, as handle_fields was given
--     it. The "@" keeps a session from ever colliding with a player name, which Luanti
--     builds out of letters, digits, dash and underscore only.
-- @param tbl (table) - The payload.
function miney_reply(who, tbl)
    if not answers then
        return
    end
    local ok, line = pcall(minetest.write_json, {session = string.sub(who, 2), data = tbl})
    if not ok or line == nil then
        line = minetest.write_json({
            session = string.sub(who, 2),
            data = {error = "Miney could not turn this answer into JSON: " .. tostring(line)},
        })
    end
    -- write_json escapes newlines inside strings, so this never fires. It is here
    -- because a raw newline would not shorten a record, it would split it into two
    -- unparseable ones and desynchronise the log for the rest of the session.
    line = string.gsub(line, "[\r\n]", " ")
    answers:write(line, "\n")
    dirty = true
end

local function drop_session(id, why)
    sessions[id] = nil
    if forget then
        forget("@" .. id)
    end
    log("action", "Session " .. id .. " " .. why .. ".")
end

-- One record from c2s. Everything it can be wrong about is answered on s2c, because a
-- request that vanishes without a word is the one failure a beginner cannot debug.
local function handle_record(line)
    -- An empty line is what a client sends when it attaches, to close off a record
    -- some earlier process died halfway through. Nothing arrived and nothing is
    -- wrong, so it must not reach parse_json - which would print three lines of
    -- engine error into the server log for every ordinary connect.
    if line == "" or string.match(line, "^%s*$") then
        return
    end

    local ok, record = pcall(minetest.parse_json, line)
    if not ok or type(record) ~= "table" then
        log("warning", "Ignored an unparseable request.")
        return
    end
    local id = record.session
    if type(id) ~= "string" or id == "" then
        log("warning", "Ignored a request without a session.")
        return
    end

    local known = sessions[id] ~= nil
    sessions[id] = os.time()

    if record.op == "bye" then
        drop_session(id, "said goodbye")
        return
    end
    if record.op == "hello" then
        if known then
            -- A second hello under the same id is a Python process that restarted
            -- without saying goodbye. Its old sandbox and its old timers are not
            -- wanted; the id is.
            if forget then forget("@" .. id) end
        end
        miney_reply("@" .. id, {ok = true, action = "hello", mod_api = advertised_api})
        return
    end
    if record.op == "ping" then
        return
    end
    if type(record.fields) == "table" and dispatch then
        dispatch("@" .. id, record.fields)
    end
end

-- Everything that has appeared in c2s since the last step, up to the time budget.
--
-- Deliberately one read of one snapshot. read_off only ever moves past a line that had
-- its terminator, so a request caught mid-write is simply seen whole next time.
local function pump()
    if not requests then
        return
    end

    local size = requests:seek("end")
    if size < read_off then
        -- The request log got shorter than this mod has already read, which means
        -- something started it over behind our back. Reading on from the old offset
        -- would land in the middle of a record, so start over too.
        read_off = 0
        log("action", "The request log was started over; reading it from the beginning.")
    end
    if size == read_off then
        return
    end

    requests:seek("set", read_off)
    local chunk = requests:read("*a") or ""

    local deadline = minetest.get_us_time() + STEP_BUDGET_US
    local pos = 1
    while true do
        local stop = string.find(chunk, "\n", pos, true)
        if not stop then
            break
        end
        handle_record(string.sub(chunk, pos, stop - 1))
        pos = stop + 1
        if minetest.get_us_time() > deadline then
            break
        end
    end
    read_off = read_off + (pos - 1)
end

local function expire_sessions()
    local now = os.time()
    for id, seen in pairs(sessions) do
        if now - seen > SESSION_TIMEOUT then
            drop_session(id, "went away without saying goodbye")
        end
    end
end

--- Start the channel.
--
-- @param dispatch_fn (function) - Called as (who, fields) with a request's fields.
-- @param forget_fn (function) - Called as (who) when a session ends, for cleanup.
-- @param mod_api (number) - The contract version to advertise in the beacon.
function miney_channel.start(dispatch_fn, forget_fn, mod_api)
    dispatch = dispatch_fn
    forget = forget_fn
    advertised_api = mod_api

    minetest.register_on_mods_loaded(function()
        -- Both logs are emptied here and nowhere else, and this is the one moment when
        -- that is unambiguous: nothing is attached to a server that has not finished
        -- loading, so neither file has a reader whose offset could be left pointing
        -- into the middle of a record.
        --
        -- ponytail: that also puts a ceiling on how large they get - one server uptime,
        -- not one machine's lifetime. Compacting them while a session is running needs
        -- a handshake in both directions, because either side truncating a file the
        -- other is reading is a race that a poll interval only usually wins. If a
        -- long-running server ever fills a disk with these, that handshake is the fix;
        -- until then the restart is.
        for _, path in ipairs({c2s_path, s2c_path}) do
            local blank = io.open(path, "w")
            if blank then blank:close() end
        end
        requests = io.open(c2s_path, "r")
        answers = io.open(s2c_path, "a")
        if not requests or not answers then
            log("error", "Could not open the channel files in " .. dir ..
                ". Miney's Python side will not be able to reach this server.")
            return
        end
        read_off = 0

        -- The beacon is how Python finds this server at all: it knows path_user and
        -- nothing else. One fsync per server start is a price worth paying for a file
        -- that must survive a crash intact.
        minetest.safe_file_write(beacon_path, minetest.write_json({
            mod_api = mod_api,
            engine = (minetest.get_version() or {}).string or "",
            world = minetest.get_worldpath(),
            world_name = string.match(minetest.get_worldpath(), "([^/\\]+)[/\\]*$") or "",
            dir = dir,
            singleplayer = minetest.is_singleplayer(),
            started = os.time(),
        }))
        log("action", "Channel open at " .. dir .. ".")
    end)

    minetest.register_globalstep(function()
        pump()
        if dirty then
            answers:flush()
            dirty = false
        end
    end)

    -- Once a second is often enough for a timeout measured in tens of them, and it
    -- keeps the per-step cost at the one seek the pump already does.
    local function tick()
        expire_sessions()
        minetest.after(1, tick)
    end
    minetest.after(1, tick)

    minetest.register_on_shutdown(function()
        -- A beacon left behind by a killed server is exactly what Python cannot tell
        -- from a live one, so the orderly case at least cleans up after itself.
        os.remove(beacon_path)
        if answers then answers:flush() end
    end)
end

return miney_channel
