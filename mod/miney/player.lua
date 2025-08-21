-- Standard animation frames for the default player model.
-- These can be adjusted if a custom player model is used.
local default_player_animations = {
    stand = {x = 0, y = 79},   -- Animation frames for standing
    walk = {x = 168, y = 187}, -- Animation frames for walking
    speed = 30,                -- Default animation speed
    blend = 0                  -- Animation blending (usually 0)
}

---
-- Moves a player smoothly to a new position and/or changes their look direction.
-- This function can animate movement, look direction, or both simultaneously.
--
-- @param player (ObjectRef) - The player object to move.
-- @param params (table) - A table containing the movement and look parameters:
--      Movement (optional):
--      - destination (vector): The absolute world coordinate to move to.
--        OR
--      - distance (number): The distance in nodes to move forward.
--
--      Look Direction (optional):
--      - look_at (vector): A world coordinate to look at. Overrides yaw/pitch.
--      - yaw (number): The final horizontal look angle (in radians).
--      - pitch (number): The final vertical look angle (in radians).
--
--      Animation settings:
--      - duration (number): The total time the animation should take in seconds. (Default: 1.0)
--      - step_interval (number): The time between each animation step. (Default: 0.05)
--      - animation (boolean): Whether to play walk/stand animations. (Default: true)
--
function smooth_move(player, params)
    -- Validate that there is something to do
    if not player or not params or
       (not params.destination and not params.distance and not params.look_at and not params.yaw and not params.pitch) then
        minetest.log("error", "[smooth_move] Invalid parameters: At least one action (destination, distance, look_at, yaw, pitch) is required.")
        return
    end

    -- Default values
    local duration = params.duration or 1.0
    local step_interval = params.step_interval or 0.05
    local num_steps = math.max(1, math.floor(duration / step_interval))
    local current_step = 0
    local use_player_animation = params.animation
    if use_player_animation == nil then
        use_player_animation = true
    end

    -- Initial state
    local start_pos = player:get_pos()
    local start_yaw = player:get_look_horizontal()
    local start_pitch = player:get_look_vertical()

    -- Target state calculation
    local target_pos, target_yaw, target_pitch
    local do_move, do_look = false, false

    -- Position
    if params.destination then
        target_pos = params.destination
        do_move = true
    elseif params.distance then
        local look_dir = player:get_look_dir()
        target_pos = vector.add(start_pos, vector.multiply(look_dir, params.distance))
        do_move = true
    end

    -- Look direction
    if params.look_at then
        local direction = vector.direction(start_pos, params.look_at)
        local rotation = vector.dir_to_rotation(direction)
        target_yaw = rotation.y
        target_pitch = rotation.x
        do_look = true
    else
        if params.yaw or params.pitch then
            target_yaw = params.yaw or start_yaw
            target_pitch = params.pitch or start_pitch
            do_look = true
        end
    end

    -- Set walk animation if moving
    if do_move and use_player_animation then
        player:set_animation(default_player_animations.walk, default_player_animations.speed, default_player_animations.blend, true)
    end

    -- Pre-calculate step vectors
    local step_vector
    if do_move then
        local total_movement = vector.subtract(target_pos, start_pos)
        step_vector = vector.divide(total_movement, num_steps)
    end

    local step_yaw, step_pitch
    if do_look then
        step_yaw = (target_yaw - start_yaw) / num_steps
        step_pitch = (target_pitch - start_pitch) / num_steps
    end

    -- Animation step function
    local function animation_step()
        current_step = current_step + 1

        if current_step > num_steps then
            -- Animation finished: set final state to correct inaccuracies
            if do_move then player:set_pos(target_pos) end
            if do_look then
                player:set_look_horizontal(target_yaw)
                player:set_look_vertical(target_pitch)
            end
            -- Set animation back to stand
            if do_move and use_player_animation then
                player:set_animation(default_player_animations.stand, default_player_animations.speed, default_player_animations.blend, true)
            end
            return -- End animation
        end

        -- Apply next step
        if do_move then
            local next_pos = vector.add(start_pos, vector.multiply(step_vector, current_step))
            player:set_pos(next_pos)
        end
        if do_look then
            player:set_look_horizontal(start_yaw + step_yaw * current_step)
            player:set_look_vertical(start_pitch + step_pitch * current_step)
        end

        minetest.after(step_interval, animation_step)
    end

    -- Start animation
    animation_step()
end
