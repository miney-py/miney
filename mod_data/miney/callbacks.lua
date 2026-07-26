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

-- The name of whoever a callback hands us, as a plain string.
--
-- Two things can go missing here and neither is an error: a node dug by a mod has no
-- digger at all, and ObjectRef:get_player_name() answers "" for anything that is not a
-- player - a mob punching someone, an arrow. Both arrive as "".
local function object_name(obj)
    if obj == nil then
        return ""
    end
    return obj:get_player_name() or ""
end

-- A position as three plain numbers.
--
-- Luanti hands out vectors with a metatable, and write_json would carry whatever else
-- is attached to them across the wire. Only x, y and z are anybody's business.
local function point(pos)
    return {x = pos.x, y = pos.y, z = pos.z}
end

-- Every event a client can subscribe to.
--
-- `on` is the Luanti registrar, `fields` turns its arguments into the payload the Python
-- side receives, and `keys` names the fields a filter may match on. Adding an event means
-- adding an entry here: the registration, the filtering and the dispatch below are
-- written once and do not grow with the list.
--
-- The payload keys are spelled the way miney/events.py spells its attributes, so an event
-- travels from Luanti into a Python attribute without being renamed anywhere on the way.
local EVENTS = {
    chat_message = {
        on = minetest.register_on_chat_message,
        keys = {"sender_name", "message"},
        fields = function(name, message)
            return {sender_name = name, message = message}
        end,
    },
    player_joins = {
        on = minetest.register_on_joinplayer,
        keys = {"player_name", "last_login"},
        fields = function(player, last_login)
            return {player_name = player:get_player_name(), last_login = last_login}
        end,
    },
    player_leaves = {
        on = minetest.register_on_leaveplayer,
        keys = {"player_name", "timed_out"},
        fields = function(player, timed_out)
            return {player_name = player:get_player_name(), timed_out = timed_out}
        end,
    },
    node_dug = {
        on = minetest.register_on_dignode,
        keys = {"pos", "node_name", "player_name"},
        fields = function(pos, oldnode, digger)
            return {pos = point(pos), node_name = oldnode.name,
                    player_name = object_name(digger)}
        end,
    },
    node_placed = {
        on = minetest.register_on_placenode,
        keys = {"pos", "node_name", "player_name"},
        fields = function(pos, newnode, placer)
            return {pos = point(pos), node_name = newnode.name,
                    player_name = object_name(placer)}
        end,
    },
    node_punched = {
        on = minetest.register_on_punchnode,
        keys = {"pos", "node_name", "player_name"},
        fields = function(pos, node, puncher)
            return {pos = point(pos), node_name = node.name,
                    player_name = object_name(puncher)}
        end,
    },
    player_dies = {
        on = minetest.register_on_dieplayer,
        keys = {"player_name", "reason"},
        fields = function(player, reason)
            return {player_name = object_name(player),
                    reason = (reason and reason.type) or "unknown"}
        end,
    },
    player_respawns = {
        on = minetest.register_on_respawnplayer,
        keys = {"player_name"},
        fields = function(player)
            return {player_name = object_name(player)}
        end,
    },
    player_punched = {
        on = minetest.register_on_punchplayer,
        keys = {"player_name", "hitter_name", "damage"},
        fields = function(player, hitter, time_from_last_punch, tool_capabilities, dir, damage)
            return {player_name = object_name(player), hitter_name = object_name(hitter),
                    damage = damage or 0}
        end,
    },
    player_hp_changed = {
        -- The second argument is what makes this a *logger* rather than a modifier. A
        -- modifier has to return the hp change it wants, and that answer would have to
        -- come back from Python from inside the callback, with the server waiting. A
        -- logger is only told what happened, which is all this can promise.
        on = function(handler)
            minetest.register_on_player_hpchange(handler, false)
        end,
        keys = {"player_name", "hp_change", "hp", "reason"},
        fields = function(player, hp_change, reason)
            -- The engine applies the change *after* the loggers have run, so get_hp()
            -- here still answers with the health from before it - reporting that as 'hp'
            -- would say "20 left" to somebody who just took four damage. So the value is
            -- worked out, and kept inside the range the game allows: a hit that takes
            -- more than is left ends at 0, not below.
            local maximum = (player:get_properties() or {}).hp_max or 20
            local after = math.max(0, math.min(player:get_hp() + hp_change, maximum))
            return {
                player_name = object_name(player),
                hp_change = hp_change,
                hp = after,
                reason = (reason and reason.type) or "unknown",
            }
        end,
    },
}

-- [client_id] = { player = "<name>", subs = { chat_message = { [handler_id] = {filter = {...}} } }, cmds = { [name] = true } }
local miney_cb = {
    clients = {},
    -- [public_name] = { client_id = "<uuid>", def = { ... } }
    commands = {}
}

local function event_names()
    local names = {}
    for name in pairs(EVENTS) do
        names[#names + 1] = name
    end
    table.sort(names)
    return table.concat(names, ", ")
end

local function is_scalar(value)
    local kind = type(value)
    return kind == "string" or kind == "number" or kind == "boolean"
end

-- One value, or a list of values, and every one of them something that can be compared
-- with '=='.
--
-- Anything else is refused rather than accepted and never matched. A position is the
-- case that makes this necessary: {pos = {x = 1, y = 2, z = 3}} looks like a perfectly
-- sensible filter, and matches() would read that table as a list of accepted values,
-- find no numbered entries in it and reject every event for the rest of the session -
-- in silence, because nothing about "no events ever" says why.
local function valid_filter_value(want)
    if is_scalar(want) then
        return true
    end
    if type(want) ~= "table" then
        return false
    end
    local count = 0
    for _ in pairs(want) do
        count = count + 1
    end
    if count == 0 then
        return false
    end
    for index = 1, count do
        if not is_scalar(want[index]) then
            return false
        end
    end
    return true
end

-- A filter naming a field its event never sends would match nothing and say nothing
-- about it, so it is refused at subscription time instead of at delivery time.
local function valid_filter(event_name, filter)
    if filter == nil then
        return true
    end
    if type(filter) ~= "table" then
        return nil, "A filter must be a table of field names and values."
    end
    local allowed = {}
    for _, key in ipairs(EVENTS[event_name].keys) do
        allowed[key] = true
    end
    for key, want in pairs(filter) do
        if not allowed[key] then
            return nil, ("Event '%s' has no field '%s'. It sends: %s."):format(
                event_name, tostring(key), table.concat(EVENTS[event_name].keys, ", "))
        end
        if not valid_filter_value(want) then
            return nil, ("Filter '%s' has to be a string, a number, a boolean or a list "
                .. "of those. A position or any other table cannot be compared this way; "
                .. "let the event through and decide in your own code."):format(tostring(key))
        end
    end
    return true
end

-- A filter is a flat table of payload field -> accepted value, or field -> list of
-- accepted values. Every field has to match; no filter accepts everything.
--
-- Deliberately no ranges and no areas. The one event that needs an area filter is
-- player_moves, which needs a rate limit in the same breath, and both belong to that
-- event rather than here.
local function matches(filter, payload)
    if filter == nil then
        return true
    end
    for key, want in pairs(filter) do
        local have = payload[key]
        if type(want) == "table" then
            local hit = false
            for _, one in ipairs(want) do
                if one == have then
                    hit = true
                    break
                end
            end
            if not hit then
                return false
            end
        elseif want ~= have then
            return false
        end
    end
    return true
end

local function anyone_wants(event_name)
    for _, rec in pairs(miney_cb.clients) do
        local subs = rec.subs and rec.subs[event_name]
        if subs and next(subs) ~= nil then
            return true
        end
    end
    return false
end

-- The single way an event leaves this mod.
--
-- One connection can watch the same event from several handlers that disagree about what
-- is interesting, so every handler is its own subscription with its own filter, and the
-- message names the handlers it is for. That keeps the whole comparison here: the Python
-- side is told which of its functions this event is meant for and does not have to work
-- it out a second time from the filters it once sent.
--
-- Still one message however many handlers match. Every event costs a formspec, and that
-- channel carries the results of lua.run as well.
local function broadcast(event_name, payload)
    for client_id, rec in pairs(miney_cb.clients) do
        local subs = rec.subs and rec.subs[event_name]
        if subs then
            local handlers = {}
            for handler_id, sub in pairs(subs) do
                if matches(sub.filter, payload) then
                    handlers[#handlers + 1] = handler_id
                end
            end
            if #handlers > 0 then
                send_callbacks_json(rec.player, {
                    event = event_name,
                    payload = payload,
                    ts = os.time(),
                    client_id = client_id,
                    handlers = handlers,
                })
            end
        end
    end
end

-- Hook every event into Luanti, once, while the mod loads. Luanti has no unregister for
-- these - builtin/game/register.lua only ever appends - so registration cannot depend on
-- anyone being interested yet. anyone_wants() is what makes that free: with nobody
-- subscribed the handler walks an empty table and returns, and the payload for the event
-- is never built.
--
-- The wrapper returns nothing on purpose. A truthy return from an on_chat_message
-- handler would swallow the message. An event whose return value the engine actually
-- reads - register_on_prejoinplayer, the allow_* family - cannot be listed in EVENTS at
-- all, because the answer would have to come back from Python from inside the callback.
local function register_events()
    for name, ev in pairs(EVENTS) do
        ev.on(function(...)
            if anyone_wants(name) then
                broadcast(name, ev.fields(...))
            end
        end)
    end
end

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
        local handler_id = req.handler
        if type(handler_id) ~= "string" or handler_id == "" then
            send_cb_error(player_name, "Missing 'handler' in request.", client_id, "bad_request")
            return true
        end
        -- Everything is checked before anything is stored, so a rejected request leaves
        -- no half-finished subscription behind.
        for _, ev in ipairs(events) do
            if not EVENTS[ev] then
                send_cb_error(player_name, ("Unknown event '%s'. Available: %s."):format(
                    tostring(ev), event_names()), client_id, "bad_request")
                return true
            end
            local filter_ok, why = valid_filter(ev, req.filter)
            if not filter_ok then
                send_cb_error(player_name, why, client_id, "bad_request")
                return true
            end
        end
        for _, ev in ipairs(events) do
            rec.subs[ev] = rec.subs[ev] or {}
            rec.subs[ev][handler_id] = {filter = req.filter}
        end
        log("action", ("register: client_id=%s, handler=%s, events_count=%d, filtered=%s"):format(
            client_id, handler_id, #(req.events or {}), tostring(req.filter ~= nil)))
        send_cb_ack(player_name, action, client_id)
        return true

    elseif action == "unregister" then
        local events = req.events or {}
        if type(events) ~= "table" then
            send_cb_error(player_name, "Field 'events' must be a list.", client_id, "bad_request")
            return true
        end
        -- Without a handler this drops every subscription for the event, which is what
        -- a client shutting down sends.
        local handler_id = req.handler
        for _, ev in ipairs(events) do
            if EVENTS[ev] and rec.subs[ev] then
                if handler_id then
                    rec.subs[ev][handler_id] = nil
                    if next(rec.subs[ev]) == nil then
                        rec.subs[ev] = nil
                    end
                else
                    rec.subs[ev] = nil
                end
            end
        end
        log("action", ("unregister: client_id=%s, handler=%s, events_count=%d"):format(
            client_id, tostring(handler_id), #(req.events or {})))
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
                    payload = { command_name = name, issuer = issuer, param = param or "" },
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

register_events()

-- After register_events(), and that is not cosmetic: Luanti runs leave handlers in
-- registration order, so the player_leaves event goes out while the leaving client's
-- subscriptions still exist. Tearing them down first would drop the last event.
minetest.register_on_leaveplayer(function(player, timed_out)
    local player_name = player:get_player_name()
    log("action", ("on_leaveplayer: player=%s, timed_out=%s"):format(player_name, tostring(timed_out)))
    cleanup_player_callbacks(player_name)
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
