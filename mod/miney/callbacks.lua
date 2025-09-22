-- Encapsulates callback-related state and behaviors for the miney mod.

local modname = minetest.get_current_modname()
local LOG_LEVELS = { error = 1, warning = 2, action = 3, info = 4, verbose = 5 }
local LOG_LEVEL_DEFAULT = "info"
local LOG_LEVEL = (function()
    local val = (minetest.settings:get("miney_log_level") or LOG_LEVEL_DEFAULT):lower()
    return LOG_LEVELS[val] or LOG_LEVELS.info
end)()

local function log(level, message)
    local lvl = LOG_LEVELS[(level or LOG_LEVEL_DEFAULT):lower()] or LOG_LEVELS.info
    if lvl <= LOG_LEVEL then
        minetest.log(level, "[" .. modname .. "/callbacks] " .. message)
    end
end

local function is_local_address(addr)
    return addr == "::ffff:127.0.0.1" or addr == "127.0.0.1"
end

local function chat_send_to_priv(priv_name, message)
    local priv_table = { [priv_name] = true }
    for _, player in ipairs(minetest.get_connected_players()) do
        if minetest.check_player_privs(player:get_player_name(), priv_table) then
            minetest.chat_send_player(player:get_player_name(), message)
        end
    end
end

local function send_callbacks_json(player_name, tbl)
    local client_info = minetest.get_player_information(player_name) or {}
    if client_info and client_info.version_string == "miney_v1.0" then
        minetest.show_formspec(player_name, "miney:code_form", minetest.write_json(tbl))
    end
end

local function send_cb_ack(player_name, action, client_id)
    send_callbacks_json(player_name, { ok = true, action = tostring(action), client_id = client_id })
end

local function send_cb_error(player_name, message, client_id, code)
    local payload = { error = tostring(message) }
    if client_id then payload.client_id = client_id end
    if code then payload.code = code end
    send_callbacks_json(player_name, payload)
end

local function valid_chatcommand_name(name)
    return type(name) == "string" and name:match("^[a-z0-9_:+%-]+$") ~= nil
end

-- [client_id] = { player = "<name>", subs = { chat_message = true }, cmds = { [name] = true } }
local miney_cb = {
    clients = {},
    -- [public_name] = { client_id = "<uuid>", def = { ... } }
    commands = {}
}

local function cleanup_player_callbacks(player_name)
    local to_unregister = {}
    local removed_clients, unreg_cmds = 0, 0
    for client_id, rec in pairs(miney_cb.clients) do
        if rec.player == player_name then
            if rec.cmds then
                for cmd_name, _ in pairs(rec.cmds) do
                    to_unregister[cmd_name] = true
                end
            end
            miney_cb.clients[client_id] = nil
            removed_clients = removed_clients + 1
        end
    end
    for cmd_name, _ in pairs(miney_cb.commands) do
        if to_unregister[cmd_name] then
            minetest.unregister_chatcommand(cmd_name)
            miney_cb.commands[cmd_name] = nil
            unreg_cmds = unreg_cmds + 1
        end
    end
    log("info", ("cleanup_player_callbacks: player=%s, removed_clients=%d, unregistered_cmds=%d")
        :format(player_name, removed_clients, unreg_cmds))
end

local function handle_receive_fields(player, fields)
    local player_name = player:get_player_name()
    local client_info = minetest.get_player_information(player_name) or {}
    local client_ip = client_info.address
    local payload_len = (fields.payload and #fields.payload) or 0
    log("action", ("handle_receive_fields: player=%s, payload_len=%d"):format(player_name, payload_len))

    if not is_local_address(client_ip) and not minetest.check_player_privs(player_name, { miney = true }) then
        local msg = "Permission denied: You lack the 'miney' privilege to manage callbacks."
        chat_send_to_priv("privs",
            "Player '" .. player_name .. "' tried to manage callbacks but lacks the 'miney' privilege. " ..
            "To grant access, use: /grant " .. player_name .. " miney"
        )
        log("warning", ("Permission denied for %s (ip=%s)"):format(player_name, tostring(client_ip)))
        send_cb_error(player_name, msg, nil, "forbidden")
        return true
    end

    local payload_json = fields.payload
    if not payload_json or payload_json == "" then
        send_cb_error(player_name, "Missing JSON payload in 'payload' field.", nil, "bad_request")
        return true
    end

    local ok, req = pcall(minetest.parse_json, payload_json)
    if not ok or type(req) ~= "table" then
        send_cb_error(player_name, "Invalid JSON payload.", nil, "bad_request")
        return true
    end
    log("info", ("request parsed: action=%s, client_id=%s"):format(tostring(req and req.action), tostring(req and req.client_id)))

    local action = req.action
    local client_id = req.client_id
    if type(client_id) ~= "string" or client_id == "" then
        send_cb_error(player_name, "Missing 'client_id' in request.", nil, "bad_request")
        return true
    end

    local rec = miney_cb.clients[client_id]
    if not rec then
        rec = { player = player_name, subs = {}, cmds = {} }
        miney_cb.clients[client_id] = rec
    else
        rec.player = player_name
    end

    if action == "register" then
        local events = req.events or {}
        if type(events) ~= "table" then
            send_cb_error(player_name, "Field 'events' must be a list.", client_id, "bad_request")
            return true
        end
        for _, ev in ipairs(events) do
            if ev == "chat_message" then
                rec.subs.chat_message = true
            end
        end
        log("action", ("register: client_id=%s, events_count=%d"):format(client_id, #(req.events or {})))
        send_cb_ack(player_name, action, client_id)
        return true

    elseif action == "unregister" then
        local events = req.events or {}
        if type(events) ~= "table" then
            send_cb_error(player_name, "Field 'events' must be a list.", client_id, "bad_request")
            return true
        end
        for _, ev in ipairs(events) do
            if ev == "chat_message" then
                rec.subs.chat_message = nil
            end
        end
        log("action", ("unregister: client_id=%s, events_count=%d"):format(client_id, #(req.events or {})))
        send_cb_ack(player_name, action, client_id)
        return true

    elseif action == "register_chatcommand" then
        local name = req.name
        local def = req.definition or {}
        if not valid_chatcommand_name(name) then
            send_cb_error(player_name, "Invalid chat command name.", client_id, "bad_request")
            return true
        end
        if miney_cb.commands[name] and miney_cb.commands[name].client_id ~= client_id then
            send_cb_error(player_name, "Chat command already registered: " .. name, client_id, "conflict")
            return true
        end

        local params = type(def.params) == "string" and def.params or ""
        local description = type(def.description) == "string" and def.description or ("Miney command '" .. name .. "'")
        local privs = type(def.privs) == "table" and def.privs or {}

        log("action", ("register_chatcommand: name=%s, client_id=%s"):format(name, client_id))
        minetest.register_chatcommand(name, {
            params = params,
            description = description,
            privs = privs,
            func = function(issuer, param)
                log("action", ("chatcommand invoked: name=%s, issuer=%s, param=%s"):format(name, issuer, param or ""))
                local event = {
                    event = "chatcommand",
                    payload = { name = name, issuer = issuer, param = param or "" },
                    ts = os.time(),
                    client_id = client_id,
                }
                send_callbacks_json(rec.player, event)
                return true
            end
        })

        miney_cb.commands[name] = { client_id = client_id, def = def }
        log("info", ("chatcommand registered: name=%s"):format(name))
        rec.cmds[name] = true
        send_cb_ack(player_name, action, client_id)
        return true

    elseif action == "unregister_chatcommand" then
        local name = req.name
        if type(name) ~= "string" or name == "" then
            send_cb_error(player_name, "Missing or invalid 'name' for unregister_chatcommand.", client_id, "bad_request")
            return true
        end
        local meta = miney_cb.commands[name]
        if not meta or meta.client_id ~= client_id then
            send_cb_error(player_name, "Chat command not owned or not found: " .. name, client_id, "not_found")
            return true
        end
        log("action", ("unregister_chatcommand: name=%s, client_id=%s"):format(name, client_id))
        minetest.unregister_chatcommand(name)
        miney_cb.commands[name] = nil
        rec.cmds[name] = nil
        send_cb_ack(player_name, action, client_id)
        return true
    else
        log("warning", ("Unknown action received: %s"):format(tostring(action)))
        send_cb_error(player_name, "Unknown action: " .. tostring(action), client_id, "bad_request")
        return true
    end
end

-- Broadcast chat messages to subscribed Miney clients
minetest.register_on_chat_message(function(name, message)
    local delivered = 0
    for client_id, rec in pairs(miney_cb.clients) do
        if rec.subs and rec.subs.chat_message then
            local event = {
                event = "chat_message",
                payload = { name = name, message = message },
                ts = os.time(),
                client_id = client_id,
            }
            send_callbacks_json(rec.player, event)
            delivered = delivered + 1
        end
    end
    log("info", ("on_chat_message: name=%s, delivered=%d"):format(name, delivered))
    return false
end)

-- Cleanup on player leave
minetest.register_on_leaveplayer(function(player)
    log("action", ("on_leaveplayer: player=%s"):format(player:get_player_name()))
    cleanup_player_callbacks(player:get_player_name())
end)

-- Cleanup on shutdown
minetest.register_on_shutdown(function()
    log("action", "callbacks: shutdown cleanup starting")
    for name, _ in pairs(miney_cb.commands) do
        minetest.unregister_chatcommand(name)
    end
    miney_cb.commands = {}
    miney_cb.clients = {}
end)

return {
    handle_receive_fields = handle_receive_fields,
    cleanup_player_callbacks = cleanup_player_callbacks,
}
