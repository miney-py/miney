-- miney mod
-- Handles form communication and Lua code execution for authorized users.

local modname = minetest.get_current_modname()
local LOG_LEVELS = { error = 1, warning = 2, action = 3, info = 4, verbose = 5 }
local LOG_LEVEL_DEFAULT = "info"
local LOG_LEVEL = (function()
    local val = (minetest.settings:get("miney_log_level") or LOG_LEVEL_DEFAULT):lower()
    return LOG_LEVELS[val] or LOG_LEVELS.info
end)()

-- Formspec related variables
local form_version = 4

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
local MOD_API = 1

-- Logger function for consistent logging
local function log(level, message)
    local lvl = LOG_LEVELS[(level or LOG_LEVEL_DEFAULT):lower()] or LOG_LEVELS.info
    if lvl <= LOG_LEVEL then
        minetest.log(level, "[" .. modname .. "] " .. message)
    end
end

local function enforce_min_engine_version(required)
    -- Ensure engine version is at least required (e.g., {5,7,0})
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

enforce_min_engine_version({5, 7, 0})

local function is_local_address(addr)
    return addr == "::ffff:127.0.0.1" or addr == "127.0.0.1"
end

-- The Miney client identifies itself by the version string it sends in
-- TOSERVER_CLIENT_READY. The engine keeps that per connection, so this is the one
-- way to tell a script's session apart from a person with a real client.
local function is_miney_client(player_name)
    local client_info = minetest.get_player_information(player_name) or {}
    return client_info.version_string == "miney_v1.0"
end

-- Miney logs in as a real player account, so every script start and stop announced
-- "*** Miney joined the game." to everyone on the server. That is noise: nobody
-- arrived, a program connected. The engine has no switch for it, but builtin calls
-- these two through the global table (builtin/game/misc.lua), so a mod can wrap them.
--
-- Join is decided from the live connection; by the time the leave message is sent the
-- client may already be gone, so remember the name while it is still knowable.
local miney_client_names = {}
local builtin_send_join_message = minetest.send_join_message
local builtin_send_leave_message = minetest.send_leave_message

function minetest.send_join_message(player_name)
    if is_miney_client(player_name) then
        miney_client_names[player_name] = true
        log("action", "Suppressed join message for the Miney client '" .. player_name .. "'.")
        return
    end
    return builtin_send_join_message(player_name)
end

function minetest.send_leave_message(player_name, timed_out)
    if miney_client_names[player_name] then
        miney_client_names[player_name] = nil
        log("action", "Suppressed leave message for the Miney client '" .. player_name .. "'.")
        return
    end
    return builtin_send_leave_message(player_name, timed_out)
end

dofile(minetest.get_modpath(modname) .. "/player.lua")
local callbacks = dofile(minetest.get_modpath(modname) .. "/callbacks.lua")

local cached_env = nil

-- Fetched here because minetest.get_mod_storage() only works while mods load; called
-- later, from inside the sandbox, it returns nil. This is the one place in Miney where
-- a script can put something that outlives its connection, and the server restart after
-- it. It is written to the world directory, so it belongs to the world, not to a player.
local mod_storage = minetest.get_mod_storage()

-- Register the 'miney' privilege
-- Worth being blunt in the description: this is not "may use a tool", it is code
-- execution inside the server process. Grant it the way you grant /lua, not the way
-- you grant /home.
minetest.register_privilege("miney", {
    description = "Run Lua code on this server through Miney. Full mod-level access to the world - only grant to people you trust with the server itself.",
    give_to_singleplayer = false
})

-- Helper function to send a chat message to all players with a specific privilege
local function chat_send_to_priv(priv_name, message)
    local priv_table = {[priv_name] = true}
    for _, player in ipairs(minetest.get_connected_players()) do
        if minetest.check_player_privs(player:get_player_name(), priv_table) then
            minetest.chat_send_player(player:get_player_name(), message)
        end
    end
end


-- Function to show the code execution form to a player
local function show_code_form(player_name, result_table, execution_id)
    local client_info = minetest.get_player_information(player_name) or {}
    local client_ip = client_info.address
    local miney_client = is_miney_client(player_name)

    -- Handle unauthorized access first and exit early.
    if not is_local_address(client_ip) and not minetest.check_player_privs(player_name, {miney = true}) then
        log("warning", "Unauthorized player " .. player_name .. " tried to access the form.")

        -- Find admins who can help.
        local admins_with_privs = {}
        local auth_handler = minetest.get_auth_handler()
        if auth_handler and auth_handler.iterate then
            for name, _ in auth_handler:iterate() do
                if minetest.check_player_privs(name, {privs = true}) then
                    table.insert(admins_with_privs, name)
                end
            end
        end

        -- Create the error response payload.
        local error_response = {
            error = "Permission denied: You lack the 'miney' privilege to execute code.",
            admins = admins_with_privs,
            mod_api = MOD_API
        }
        if execution_id then
            error_response.execution_id = execution_id
        end

        -- Notify admins about the attempt.
        local admin_notification = "Player '" .. player_name .. "' tried to execute code but lacks the 'miney' privilege. " ..
                                  "To grant access, use: /grant " .. player_name .. " miney"
        chat_send_to_priv("privs", admin_notification)

        -- Send the appropriate response based on client type.
        if miney_client then
            minetest.show_formspec(player_name, "miney:code_form", minetest.write_json(error_response))
        else
            minetest.chat_send_player(player_name, error_response.error)
        end

        log("action", "Sent permission denied response to " .. player_name)
        return true
    end

    local response_data = result_table or {}
    -- The execution_id is now expected to be in result_table from the caller.
    if execution_id and not response_data.execution_id then
        response_data.execution_id = execution_id
    end

    -- If we reach here, the player is authorized.
    if miney_client then
        --log("action", "Sending JSON response to LuantiClient " .. player_name)

        -- Carried by every answer including the empty warm-up one, so the client knows
        -- what it is talking to before it sends the first line of code. Only for Miney:
        -- a person looking at the form has no use for it in their result box.
        response_data.mod_api = MOD_API

        local final_json_response = minetest.write_json(response_data)
        minetest.show_formspec(player_name, "miney:code_form", final_json_response)
    else
        -- For regular clients, show the standard formspec.
        local formspec = "formspec_version[" .. form_version .. "]" ..
                        "size[10,12]" ..
                        "label[0.5,0.5;Execute LUA Code:]" ..
                        "textarea[0.5,1;9,4;lua;;]" ..
                        "button[0.5,5.5;4,0.8;execute;Execute]"

        local result_text = minetest.write_json(response_data, true)
        formspec = formspec ..
                   "textarea[0.5,7;9,4;result;Result:;" ..
                   minetest.formspec_escape(result_text) .. "]"

        minetest.show_formspec(player_name, "miney:code_form", formspec)
    end

    --log("debug", "Processed form request for player " .. player_name)
    return true
end

-- One scratch table per connected player, thrown away when they leave.
--
-- The sandbox used to be a single table shared by everyone, and it was also what the
-- code wrote to. So `x = 1` in one script was still there in the next one, in every
-- other player's scripts, and until the server restarted. `minetest = nil` - one typo
-- away from `minetest = nil or something` - disabled the whole mod for the entire
-- server, including Miney's own calls.
--
-- Reads still reach the shared environment through __index, so building it once is
-- still worth it. Writes land in the player's own table and go away with them.
local player_scratch = {}

local function scratch_for(player_name)
    local scratch = player_scratch[player_name]
    if not scratch then
        scratch = setmetatable({}, {__index = cached_env})
        player_scratch[player_name] = scratch
    end
    return scratch
end

minetest.register_on_leaveplayer(function(player)
    player_scratch[player:get_player_name()] = nil
end)

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
local function execute_lua_code(code, player_name)
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
            -- by every connection, and carrying io, os.remove and require. That made
            -- the per-player scratch tables below decorative and gave anyone with the
            -- 'miney' privilege read and write access to the server's file system.
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
    setfenv(exec_func, scratch_for(player_name))

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


minetest.register_on_player_receive_fields(function(player, formname, fields)
    if formname == "miney:code_form" then
        local player_name = player:get_player_name()
        local client_info = minetest.get_player_information(player_name) or {}
        local client_ip = client_info.address

        -- Route callback requests sent via the code form
        if fields and fields.payload then
            return callbacks.handle_receive_fields(player, fields)
        end

        if not is_local_address(client_ip) and not minetest.check_player_privs(player_name, { miney = true }) then
            log("warning", "Unauthorized player " .. player_name .. " tried to submit form data.")
            show_code_form(player_name, nil, fields.execution_id)
            return true
        end

        local execution_id = fields.execution_id
        if fields.execute and fields.lua and fields.lua ~= "" then
            local result_table = execute_lua_code(fields.lua, player_name)
            if execution_id then
                result_table.execution_id = execution_id
            end
            show_code_form(player_name, result_table, nil)
        end
        return true

    end

    return false
end)


-- Register chat command handler for /miney
minetest.register_chatcommand("miney", {
    params = "<form|callbacks|help>",
    description = "Shows the Lua execution form or help.",
    func = function(name, param)
        local command = param:lower()
        if command == "form" then
            log("action", "Player " .. name .. " requested code form via command.")
            show_code_form(name)
            return true
        elseif command == "callbacks" then
            if is_miney_client(name) then
                -- Warm-up uses the code form now to keep expected formname aligned
                show_code_form(name)
                return true
            else
                minetest.chat_send_player(name, "Callbacks warm-up is only available for the Miney client.")
                return true
            end
        elseif command == "help" then
            minetest.chat_send_player(name, "Available miney commands: /miney form, /miney callbacks, /miney help")
            return true
        end
        return false, "Unknown subcommand. Use /miney help."
    end,
})



-- Initialize the mod
minetest.register_on_mods_loaded(function()
    log("action", "Initializing miney mod...")
    log("action", "Players with the 'miney' privilege can execute code.")
end)


-- Log when the mod is loaded
log("action", "miney mod loaded successfully")
