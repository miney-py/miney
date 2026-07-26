-- Somewhere to keep the handle that minetest.after hands back.
--
-- The engine can cancel a scheduled call - core.after returns a job table with
-- job:cancel() (doc/lua_api.md) - but nobody ever kept it. A function that
-- re-schedules itself therefore outlived the script that started it, the disconnect
-- and the Python process; and because every connection has its own sandbox, a later
-- session could not even read the variables the loop was built from. Only a server
-- restart stopped it.
--
-- So every timer started on behalf of a connection is registered here under that
-- connection's player name, and register_on_leaveplayer cancels whatever is left.
--
-- Deliberately not a global registry with a stop-the-world button: a timer belongs to
-- the session that asked for it, and that is the only thing that may end it.

miney_tasks = {}

-- owner -> id -> {job = <what minetest.after returned>, key = <string or nil>}
local jobs = {}
local next_id = 0

local function owned(owner)
    local mine = jobs[owner]
    if not mine then
        mine = {}
        jobs[owner] = mine
    end
    return mine
end

--- Schedule a function the way minetest.after does, but keep the handle.
--
-- The entry removes itself just before the function runs, so something that
-- re-schedules itself registers again and the table holds one entry per live chain
-- instead of one per frame ever scheduled.
--
-- @param owner (string) - The player name this timer belongs to.
-- @param delay (number) - Seconds until the call, as for minetest.after.
-- @param fn (function) - What to call.
-- @param key (string or nil) - A name to cancel it by, see cancel_key.
-- @param ... - Further arguments for fn, as for minetest.after.
-- @return (table) - A handle with :cancel(), the same shape minetest.after returns.
function miney_tasks.after(owner, delay, fn, key, ...)
    next_id = next_id + 1
    local id = next_id
    local mine = owned(owner)
    local entry = {key = key}
    mine[id] = entry

    local args = {n = select("#", ...), ...}
    entry.job = minetest.after(delay, function()
        mine[id] = nil
        fn(unpack(args, 1, args.n))
    end)

    return {cancel = function() return miney_tasks.cancel(owner, id) end}
end

--- Cancel one timer.
--
-- @param owner (string) - The player name it was registered under.
-- @param id (number) - Its id.
-- @return (boolean) - True if there was something to cancel.
function miney_tasks.cancel(owner, id)
    local mine = jobs[owner]
    local entry = mine and mine[id]
    if not entry then return false end
    mine[id] = nil
    entry.job:cancel()
    return true
end

--- Cancel every timer this owner registered under one key.
--
-- Cancelling is idempotent in the engine - job:cancel() replaces the function with an
-- empty one - so a stale key costs nothing.
--
-- @param owner (string) - The player name.
-- @param key (string) - The key given to after().
-- @return (number) - How many were cancelled.
function miney_tasks.cancel_key(owner, key)
    local mine = jobs[owner]
    if not mine then return 0 end
    local count = 0
    for id, entry in pairs(mine) do
        if entry.key == key then
            mine[id] = nil
            entry.job:cancel()
            count = count + 1
        end
    end
    return count
end

--- Is anything still scheduled under this key?
--
-- @param owner (string) - The player name.
-- @param key (string) - The key given to after().
-- @return (boolean)
function miney_tasks.busy(owner, key)
    local mine = jobs[owner]
    if not mine then return false end
    for _, entry in pairs(mine) do
        if entry.key == key then return true end
    end
    return false
end

--- Cancel everything one connection started.
--
-- @param owner (string) - The player name.
-- @return (number) - How many were cancelled.
function miney_tasks.stop_all(owner)
    local mine = jobs[owner]
    if not mine then return 0 end
    jobs[owner] = nil
    local count = 0
    for _, entry in pairs(mine) do
        entry.job:cancel()
        count = count + 1
    end
    return count
end

-- The one thing that makes all of the above worth having. A Miney session always ends
-- here, whether it disconnected properly, timed out or its process was killed, so
-- there is no state a runaway loop can survive in.
minetest.register_on_leaveplayer(function(player)
    local name = player:get_player_name()
    local count = miney_tasks.stop_all(name)
    if count > 0 then
        minetest.log("action", "[miney] Cancelled " .. count .. " timer(s) left by " .. name .. ".")
    end
end)

return miney_tasks
