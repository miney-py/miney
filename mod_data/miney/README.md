# Miney Mod for Luanti

A simple mod that allows authorized clients to execute Lua code via a formspec.

## Features

- Provides a form (`miney:code_form`) for executing Lua code.
- Uses Minetest's privilege system for authorization (requires the `miney` privilege).
- Notifies admins (players with `privs` privilege) of unauthorized access attempts.
- Responds to chat commands via `/miney`.

## Commands

- `/miney help` - Shows available commands.
- `/miney form` - Opens the Lua code execution form.

## Usage with Python Client

This mod is designed to work with the Luanti Python client. To use the code execution features, the player corresponding to the client must have the `miney` privilege.

An admin can grant this privilege using the chat command:
`/grant <playername> miney`
