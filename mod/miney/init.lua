-- miney mod
-- Handles form communication and Lua code execution for authorized users.

local modname = minetest.get_current_modname()

-- Formspec related variables
local form_version = 4

-- Logger function for consistent logging
local function log(level, message)
    minetest.log(level, "[" .. modname .. "] " .. message)
end

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
    local client_info = minetest.get_player_information(player_name)
    local client_ip = client_info.address
    local is_miney_client = client_info and client_info.version_string == "miney_v1.0"

    -- Handle unauthorized access first and exit early.
    if client_ip ~= "::ffff:127.0.0.1" and not minetest.check_player_privs(player_name, {miney = true}) then
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

    -- If we reach here, the player is authorized.
    if is_miney_client then
        --log("action", "Sending JSON response to LuantiClient " .. player_name)
        
        local response_data = result_table or {}
        -- The execution_id is now expected to be in result_table from the caller.
        if execution_id and not response_data.execution_id then
            response_data.execution_id = execution_id
        end
        
        local final_json_response = minetest.write_json(response_data)
        minetest.show_formspec(player_name, "miney:code_form", final_json_response)
    else
        -- For regular clients, show the standard formspec.
        local formspec = "formspec_version[" .. form_version .. "]" ..
                        "size[10,12]" ..
                        "label[0.5,0.5;Lua-Code ausführen:]" ..
                        "textarea[0.5,1;9,4;lua;;]" ..
                        "button[0.5,5.5;4,0.8;execute;Ausführen]"
        
        if result_table then
            local result_text
            if result_table.result then
                result_text = minetest.write_json(result_table.result, true) -- Pretty print
            elseif result_table.error then
                result_text = "Error: " .. tostring(result_table.error)
            else
                -- Fallback for unexpected table structure
                result_text = minetest.write_json(result_table, true)
            end
            
            formspec = formspec ..
                      "textarea[0.5,7;9,4;result;Result:;" .. minetest.formspec_escape(result_text) .. "]"
        end

        minetest.show_formspec(player_name, "miney:code_form", formspec)
    end

    --log("debug", "Processed form request for player " .. player_name)
    return true
end

-- Function to safely execute Lua code
local function execute_lua_code(code, player_name)
    -- Create a safe environment for execution
    local env = {
        minetest = minetest,
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
        player_name = player_name,
        vector = vector,
        ItemStack = ItemStack,
        VoxelArea = VoxelArea,
        VoxelManip = VoxelManip,
        PseudoRandom = PseudoRandom,
        PcgRandom = PcgRandom,
        PerlinNoise = PerlinNoise,
        PerlinNoiseMap = PerlinNoiseMap,
        SecureRandom = SecureRandom,
    }

    -- Create a function with the safe environment
    local func, err = loadstring("return function() " .. code .. " end")
    if not func then
        return {error = "Syntax error: " .. tostring(err)}
    end

    -- Set the environment for the function
    setfenv(func, env)

    -- Execute the code and catch errors
    local success, result
    local exec_func = func()

    success, result = pcall(exec_func)

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

    -- Wrap the successful result in the standard response format
    return {result = result}
end

-- Register handler for form submissions
minetest.register_on_player_receive_fields(function(player, formname, fields)
    if formname ~= "miney:code_form" then
        return false
    end
    
    local player_name = player:get_player_name()
    local client_info = minetest.get_player_information(player_name)
    local client_ip = client_info.address
    --log("debug", "Received form input from " .. player_name)
    
    -- Check for 'miney' privilege before processing
    if client_ip ~= "::ffff:127.0.0.1" and not minetest.check_player_privs(player_name, {miney = true}) then
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
        local result_table = execute_lua_code(fields.lua, player_name)
        
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
            return true, "Code form opened."
        elseif command == "help" then
            minetest.chat_send_player(name, "Available miney commands: /miney form, /miney help")
            return true, "Help message sent."
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
