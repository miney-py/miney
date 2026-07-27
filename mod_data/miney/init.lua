-- miney mod
-- Reads Lua from the file channel, runs it in a per-session sandbox, writes the answer
-- back. channel.lua is the file half; this is what happens to a request once it lands.

local modname = minetest.get_current_modname()
local LOG_LEVELS = { error = 1, warning = 2, action = 3, info = 4, verbose = 5 }
local LOG_LEVEL_DEFAULT = "info"
local LOG_LEVEL = (function()
    local val = (minetest.settings:get("miney_log_level") or LOG_LEVEL_DEFAULT):lower()
    return LOG_LEVELS[val] or LOG_LEVELS.info
end)()

-- What this mod promises the Python side, sent with every answer so it can check once
-- and say something useful instead of failing halfway through.
--
-- Deliberately not the Miney release number. The Python package is versioned in
-- miney/__init__.py and that stays the only place to bump at release time; this counts
-- something slower - the request and response contract between the two halves. Raise it
-- when a command, a field or a name in the sandbox changes in a way an older Python
-- would not survive, and raise REQUIRED_MOD_API in miney/lua.py to match.
--
--   1  storage in the sandbox, the instruction budget, no getfenv
--   2  timers belong to the connection that started them, miney_task_busy
--   3  event payloads name their fields like miney/events.py, event filters are honoured
--   4  node and player events (node_dug, node_placed, node_punched, player_dies,
--      player_respawns, player_punched, player_hp_changed), filter values are checked
--   5  a request may arrive in several submits, numbered with "part" and "parts";
--      the engine floor is Luanti 5.9
--   6  miney_assets and miney_hud in the sandbox: pictures a script uploads, the
--      texture names the game ships, and the named HUD registry per player
--   7  the file channel: requests arrive as JSON lines on <mod_data>/miney/<world>/c2s
--      and answers leave on s2c, so a script no longer needs a player account. The
--      formspec transport is still there for a server on another machine.
--   8  the file channel is the only way in. The formspec transport, the 'miney'
--      privilege and the split-request assembly are gone, and with them the last
--      reason for this mod to know anything about players or client addresses.
local MOD_API = 8

-- Logger function for consistent logging
local function log(level, message)
    local lvl = LOG_LEVELS[(level or LOG_LEVEL_DEFAULT):lower()] or LOG_LEVELS.info
    if lvl <= LOG_LEVEL then
        minetest.log(level, "[" .. modname .. "] " .. message)
    end
end

local function enforce_min_engine_version(required)
    -- Ensure engine version is at least required (e.g., {5,9,0})
    local v = minetest.get_version and minetest.get_version() or {}
    local major, minor, patch
    if type(v.string) == "string" then
        local mj, mi, pa = string.match(v.string, "(%d+)%.(%d+)%.(%d+)")
        if mj then
            major, minor, patch = tonumber(mj), tonumber(mi), tonumber(pa)
        end
    end
    if not major then
        major = tonumber(v.major) or 0
        minor = tonumber(v.minor) or 0
        patch = tonumber(v.patch) or 0
    end
    local req_major, req_minor, req_patch = required[1], required[2], required[3]

    local too_old =
        (major < req_major) or
        (major == req_major and minor < req_minor) or
        (major == req_major and minor == req_minor and patch < req_patch)

    if too_old then
        local detected = v.string or (tostring(major) .. "." .. tostring(minor) .. "." .. tostring(patch))
        local msg = string.format(
            "Miney requires Luanti/Minetest >= %d.%d.%d, detected %s. Please upgrade the server.",
            req_major, req_minor, req_patch, detected
        )
        minetest.log("error", "[" .. modname .. "] " .. msg)
        error("[miney] " .. msg)
    end
end

enforce_min_engine_version({5, 9, 0})

-- Before player.lua: smooth_move registers its frames here.
dofile(minetest.get_modpath(modname) .. "/tasks.lua")
dofile(minetest.get_modpath(modname) .. "/player.lua")
-- Reads minetest.get_mod_data_path(), which only answers while mods load.
dofile(minetest.get_modpath(modname) .. "/assets.lua")
dofile(minetest.get_modpath(modname) .. "/hud.lua")
-- Before callbacks.lua: it defines miney_reply, which is how an event leaves the mod.
dofile(minetest.get_modpath(modname) .. "/channel.lua")
local callbacks = dofile(minetest.get_modpath(modname) .. "/callbacks.lua")

local cached_env = nil

-- Fetched here because minetest.get_mod_storage() only works while mods load; called
-- later, from inside the sandbox, it returns nil. This is the one place in Miney where
-- a script can put something that outlives its connection, and the server restart after
-- it. It is written to the world directory, so it belongs to the world, not to a player.
local mod_storage = minetest.get_mod_storage()

-- Send one answer back down the channel the request came in on.
--
-- Every answer carries the contract version, so the Python side knows what it is
-- talking to before it acts on anything.
--
-- @param session (string) - The session to answer, as handle_fields was given it.
-- @param result_table (table|nil) - What to send back.
-- @param execution_id (string|nil) - Which request this answers, when the table does
--     not already say.
local function reply(session, result_table, execution_id)
    local response_data = result_table or {}
    if execution_id and not response_data.execution_id then
        response_data.execution_id = execution_id
    end
    response_data.mod_api = MOD_API
    miney_reply(session, response_data)
    return true
end

-- One scratch table per session, thrown away when the session ends.
--
-- The sandbox used to be a single table shared by everyone, and it was also what the
-- code wrote to. So `x = 1` in one script was still there in the next one, in every
-- other script, and until the server restarted. `minetest = nil` - one typo away from
-- `minetest = nil or something` - disabled the whole mod for the entire server,
-- including Miney's own calls.
--
-- Reads still reach the shared environment through __index, so building it once is
-- still worth it. Writes land in the session's own table and go away with it.
local player_scratch = {}

local function scratch_for(session)
    local scratch = player_scratch[session]
    if not scratch then
        scratch = setmetatable({}, {__index = cached_env})

        -- A timer this session starts has to be findable again when it ends, so
        -- minetest.after is shadowed by one that keeps the handle it hands back.
        -- Everything else falls through to the real table. Code in the sandbox is
        -- written exactly as it would be in a mod; it is this side that remembers.
        scratch.minetest = setmetatable({
            after = function(delay, fn, ...)
                return miney_tasks.after(session, delay, fn, nil, ...)
            end,
        }, {__index = minetest})

        -- Bound to the caller for the same reason: its frames are this session's.
        scratch.smooth_move = function(player, params)
            return smooth_move(player, params, session)
        end

        -- How Player.move(wait=True) asks whether the animation is over. Plumbing, not
        -- something a script is meant to reach for.
        scratch.miney_task_busy = function(key)
            return miney_tasks.busy(session, key)
        end

        player_scratch[session] = scratch
    end
    return scratch
end

-- User code runs inside the server step, so for as long as it runs the whole server
-- stands still - no player moves, nothing is saved. "while true do end" used to mean
-- killing the process and losing whatever had not been written to disk yet.
--
-- The engine has no time limit to offer, but Lua counts instructions: a hook installed
-- with the "count" mask fires every N of them, whatever the code is doing, and raising
-- an error from inside it unwinds the call. The hook belongs to a coroutine, so the
-- error stops that coroutine instead of the server step, and comes back through
-- coroutine.resume in the same shape pcall would have returned.
--
-- Two things this depends on, both verified against a running server rather than
-- assumed. LuaJIT does not check hooks inside a compiled trace, and "while true do end"
-- is the first thing it compiles - with the hook alone the server froze exactly as
-- before. jit.off(exec_func, true) keeps the user's code and everything it defines in
-- the interpreter, where the hook fires. That costs nothing worth measuring here: these
-- snippets spend their time inside engine calls, not in Lua arithmetic.
--
-- Not a hard guarantee: instructions are counted in Lua, not in C, so a single engine
-- call that blocks for a minute still blocks for a minute. It catches the loop that a
-- person actually writes by accident.
--
-- The budget is counted in Lua steps rather than seconds because that is what the hook
-- offers. Measured on the test server: 20 million steps is about 0.02 s of frozen
-- server and roughly 9 million iterations of a plain arithmetic loop. 200 million buys
-- a tenth of a second in the worst case, which nobody notices, and leaves ten times the
-- headroom for a script that genuinely has work to do.
local INSTRUCTION_BUDGET = 200000000

local function resume_with_budget(exec_func)
    if jit and jit.off then
        jit.off(exec_func, true)
    end
    local co = coroutine.create(exec_func)
    debug.sethook(co, function()
        debug.sethook(co)
        error("Miney stopped this code after " .. INSTRUCTION_BUDGET .. " steps, to keep " ..
              "the server responding. Is there a loop in it that never ends?", 2)
    end, "", INSTRUCTION_BUDGET)
    local success, result = coroutine.resume(co)
    debug.sethook(co)
    return success, result
end

-- Function to safely execute Lua code
local function execute_lua_code(code, session)
    -- On the first run, build and cache the secure base environment.
    if not cached_env then
        log("action", "First run: Initializing and caching the secure Lua environment.")
        cached_env = {
            minetest = minetest,
            storage = mod_storage,
            dump = dump,
            dump2 = dump2,
            print = function(...)
                local args = {...}
                local result = ""
                for i, v in ipairs(args) do
                    if i > 1 then result = result .. "\t" end
                    result = result .. tostring(v)
                end
                return result
            end,
            tostring = tostring,
            tonumber = tonumber,
            type = type,
            -- No getfenv here on purpose. Lua 5.1 defines getfenv(0) as "the global
            -- environment", so handing it out handed out the real _G: writable, shared
            -- by every session, and carrying io, os.remove and require. That made the
            -- per-session scratch tables above decorative.
            math = math,
            string = string,
            table = table,
            os = {
                time = os.time,
                difftime = os.difftime,
                date = os.date,
                clock = os.clock,
            },
            pairs = pairs,
            ipairs = ipairs,
            next = next,
            select = select,
            unpack = unpack,
            vector = vector,
            ItemStack = ItemStack,
            VoxelArea = VoxelArea,
            VoxelManip = VoxelManip,
            PseudoRandom = PseudoRandom,
            PcgRandom = PcgRandom,
            PerlinNoise = PerlinNoise,
            PerlinNoiseMap = PerlinNoiseMap,
            SecureRandom = SecureRandom,
            smooth_move = smooth_move,
            miney_assets = miney_assets,
            miney_hud = miney_hud,
        }

        -- A list of approved prefixes for global variables from other mods.
        local allowed_prefixes = {"mcl_"}

        -- Populate the cached environment with globals that match the allowed prefixes.
        for k, v in pairs(_G) do
            if cached_env[k] == nil then
                for _, prefix in ipairs(allowed_prefixes) do
                    if string.sub(k, 1, #prefix) == prefix then
                        cached_env[k] = v
                        break
                    end
                end
            end
        end
    end

    -- Create a function that returns our sandboxed code as a closure.
    local factory_func, err = loadstring("return function() " .. code .. " end")
    if not factory_func then
        return {error = "Syntax error: " .. tostring(err)}
    end

    -- Create the actual closure. It will initially inherit the global environment.
    local exec_func = factory_func()

    -- Now, directly set the environment of the final closure to our secure sandbox.
    setfenv(exec_func, scratch_for(session))

    -- Execute the code and catch errors.
    local success, result = resume_with_budget(exec_func)

    if not success then
        return {error = "Runtime error: " .. tostring(result)}
    end

    -- Test serialization to catch errors early.
    local json_success, json_result = pcall(minetest.write_json, result)

    -- The check must verify both pcall success and that write_json did not return nil.
    if not json_success or json_result == nil then
        local error_msg
        if not json_success then
            -- This case handles errors within the write_json C++ function itself.
            error_msg = "Error during JSON serialization: " .. tostring(json_result)
        else
            -- This case handles valid Lua tables that contain non-serializable types.
            error_msg = "Failed to serialize result: The result contains non-serializable values like functions or userdata."
        end
        log("error", error_msg)
        return {error = error_msg}
    end

    -- Wrap the successful result in the standard response format.
    return {result = result}
end


-- The largest single request this mod will run. Mirrors MAX_LUA_SOURCE in
-- miney/lua.py, which refuses it before sending; this is what stops anything that does
-- not go through Miney - a runaway generator writing Lua into c2s in a loop.
local MAX_REQUEST = 16 * 1024 * 1024

-- One request off the channel.
--
-- @param session (string) - The session it came from, as channel.lua names it.
-- @param fields (table) - What the record carried.
local function handle_fields(session, fields)
    -- Subscriptions and chat command registrations travel as a JSON payload rather
    -- than as Lua source.
    if fields and fields.payload then
        return callbacks.handle_receive_fields(session, fields)
    end

    local execution_id = fields.execution_id

    if fields.execute and fields.lua and fields.lua ~= "" then
        if #fields.lua > MAX_REQUEST then
            reply(session, {error = "This Lua code is too long: the mod takes at most "
                .. MAX_REQUEST .. " bytes and this request is past it."}, execution_id)
            return true
        end
        local result_table = execute_lua_code(fields.lua, session)
        if execution_id then
            result_table.execution_id = execution_id
        end
        reply(session, result_table, nil)
    end
    return true
end

-- Everything one session left behind, thrown away when it says goodbye or falls silent:
-- a killed Python process must not leave a re-scheduling timer or a chat command
-- running on the server for the rest of the day.
local function forget_session(session)
    player_scratch[session] = nil
    local cancelled = miney_tasks.stop_all(session)
    if cancelled > 0 then
        log("action", "Cancelled " .. cancelled .. " timer(s) left by " .. session .. ".")
    end
    callbacks.cleanup_player_callbacks(session)
end

miney_channel.start(handle_fields, forget_session, MOD_API)


-- Log when the mod is loaded
log("action", "miney mod loaded successfully")
