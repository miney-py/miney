-- miney mod
-- Handles form communication and Lua code execution for authorized users.

local modname = minetest.get_current_modname()

-- Formspec related variables
local form_version = 4

-- Logger function for consistent logging
local function log(level, message)
    minetest.log(level, "[" .. modname .. "] " .. message)
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

dofile(minetest.get_modpath(modname) .. "/player.lua")

local cached_env = nil

-- Register the 'miney' privilege
minetest.register_privilege("miney", {
    description = "Allows execution of Lua code via the miney mod",
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
    local is_miney_client = client_info and client_info.version_string == "miney_v1.0"

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
            admins = admins_with_privs
        }
        if execution_id then
            error_response.execution_id = execution_id
        end

        -- Notify admins about the attempt.
        local admin_notification = "Player '" .. player_name .. "' tried to execute code but lacks the 'miney' privilege. " ..
                                  "To grant access, use: /grant " .. player_name .. " miney"
        chat_send_to_priv("privs", admin_notification)

        -- Send the appropriate response based on client type.
        if is_miney_client then
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
    if is_miney_client then
        --log("action", "Sending JSON response to LuantiClient " .. player_name)
        
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

-- Function to safely execute Lua code
local function execute_lua_code(code)
    -- On the first run, build and cache the secure base environment.
    if not cached_env then
        log("action", "First run: Initializing and caching the secure Lua environment.")
        cached_env = {
            minetest = minetest,
            dump = dump,
            dump2 = dump2,
            getfenv = getfenv,
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
    setfenv(exec_func, cached_env)

    -- Execute the code and catch errors.
    local success, result = pcall(exec_func)

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


-- Register handler for form submissions
minetest.register_on_player_receive_fields(function(player, formname, fields)
    if formname ~= "miney:code_form" then
        return false
    end
    
    local player_name = player:get_player_name()
    local client_info = minetest.get_player_information(player_name) or {}
    local client_ip = client_info.address
    --log("debug", "Received form input from " .. player_name)
    
    -- Check for 'miney' privilege before processing
    if not is_local_address(client_ip) and not minetest.check_player_privs(player_name, {miney = true}) then
        log("warning", "Unauthorized player " .. player_name .. " tried to submit form data.")
        -- Show the form again; it will contain the permission error message.
        show_code_form(player_name, nil, fields.execution_id)
        return true -- Suppress further processing
    end
    
    -- Extract the execution ID if present
    local execution_id = fields.execution_id
    
    -- Process Lua code
    if fields.execute and fields.lua and fields.lua ~= "" then
        --log("action", "Player " .. player_name .. " executing Lua code" ..
        --    (execution_id and " with ID " .. execution_id or ""))
        
        -- Execute the Lua code
        local result_table = execute_lua_code(fields.lua)
        
        -- Add execution_id to the response table
        if execution_id then
            result_table.execution_id = execution_id
        end
        
        -- Show the form with the result again
        show_code_form(player_name, result_table, nil)
        
        -- Log the result
        --log("debug", "Lua execution result: " .. minetest.write_json(result_table))
    end
    
    return true
end)

-- Register chat command handler for /miney
minetest.register_chatcommand("miney", {
    params = "<form|help>",
    description = "Shows the Lua execution form or help.",
    func = function(name, param)
        local command = param:lower()
        if command == "form" then
            log("action", "Player " .. name .. " requested code form via command.")
            show_code_form(name)
            return true
        elseif command == "help" then
            minetest.chat_send_player(name, "Available miney commands: /miney form, /miney help")
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
