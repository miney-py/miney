import sys
import os
import socket
import pprint

try:
    from miney import Luanti, exceptions
except ModuleNotFoundError:
    # Allow running the script from the project's root directory
    sys.path.append(os.getcwd())
    from miney import Luanti, exceptions


def print_welcome():
    """Prints the welcome message and instructions."""
    print("Miney Lua Console")
    print("=================")
    print("Usage: python luaconsole.py [<server> <port> <playername> <password>]")
    print("\nClient-side commands:")
    print("  !help          - Show this help message.")
    print("  !clear         - Clear the console screen.")
    print("  !run <filename>  - Execute a local Lua script file on the server.")
    print("  !exit or !quit - Exit the console.")
    print("\nLua Interaction:")
    print("  - Enter any Lua code to execute it on the server.")
    print("  - Your code runs inside a function. Use 'return <value>' to get a result.")
    print("    (For simple expressions like '1+1', 'return' is added automatically).")
    print("  - Start multiline mode with '--'. Submit with two empty lines.")
    print("  - Press Ctrl+C to exit multiline mode or the console itself.")
    print("-" * 20)


def handle_client_command(cmd: str, lt: Luanti, pp: pprint.PrettyPrinter) -> bool:
    """
    Handles client-side commands that start with '!'.

    :param cmd: The command string.
    :param lt: The Luanti instance for executing code.
    :param pp: The PrettyPrinter for displaying results.
    :return: True if the console should exit, False otherwise.
    """
    if cmd in ("!exit", "!quit"):
        return True
    elif cmd == "!help":
        print_welcome()
    elif cmd == "!clear":
        # Works on Windows (cls) and Unix-like systems (clear)
        os.system('cls' if os.name == 'nt' else 'clear')
    elif cmd.startswith("!run "):
        parts = cmd.split(" ", 1)
        if len(parts) < 2 or not parts[1].strip():
            print("<< Usage: !run <filename.lua>")
        else:
            filename = parts[1].strip()
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    lua_code = f.read()
                print(f">> Executing '{filename}'...")
                result = lt.lua.run(lua_code)
                if result is not None:
                    print("<<")
                    pp.pprint(result)
            except FileNotFoundError:
                print(f"<< Error: File not found: {filename}")
            except Exception as e:
                print(f"<< Error reading or executing file: {e}")
    else:
        print(f"<< Unknown client command: {cmd}. Type '!help' for instructions.")
    return False


def main():
    """Main function to run the Lua console."""
    # --- Connection Details ---
    server = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 30000
    playername = sys.argv[3] if len(sys.argv) > 3 else "miney"
    password = sys.argv[4] if len(sys.argv) > 4 else "ChangeThePassword!"

    # --- Connect to Server ---
    try:
        lt = Luanti(server, playername, password, port)
        print(f"Successfully connected to {server}:{port} as '{playername}'.")
    except (exceptions.LuantiConnectionError, socket.timeout) as e:
        print(f"Error: Could not connect to server. {e}", file=sys.stderr)
        sys.exit(1)

    print_welcome()

    # --- REPL Setup ---
    multiline_mode = False
    multiline_cmd = ""
    # Pretty printer for nicely formatting Lua tables (returned as Python dicts/lists)
    pp = pprint.PrettyPrinter(indent=2)

    # --- Main Loop ---
    try:
        while True:
            try:
                prompt = "-- " if multiline_mode else ">> "
                cmd = input(prompt)

                if multiline_mode:
                    multiline_cmd += cmd + "\n"
                    if "\n\n" in multiline_cmd:
                        # Execute multiline command
                        ret = lt.lua.run(multiline_cmd)
                        multiline_mode = False
                        if ret is not None:
                            print("<<")
                            pp.pprint(ret)
                else:
                    if cmd.startswith('!'):
                        if handle_client_command(cmd, lt, pp):
                            break  # Exit loop
                        continue

                    if cmd == "--":
                        multiline_mode = True
                        multiline_cmd = ""
                        continue

                    # Execute single-line command only if it's not empty
                    if cmd.strip():
                        processed_cmd = cmd.strip()
                        # A client-side heuristic to automatically add 'return' for expressions.
                        # If the command starts with a common statement keyword, we assume it's
                        # a full statement and don't modify it. Otherwise, we treat it as
                        # an expression and add 'return' for convenience.
                        LUA_STATEMENT_KEYWORDS = (
                            "return", "local", "if", "for", "while", "function", "do"
                        )
                        if not processed_cmd.startswith(LUA_STATEMENT_KEYWORDS):
                            processed_cmd = "return " + processed_cmd

                        ret = lt.lua.run(processed_cmd)
                        if ret is not None:
                            print("<<")
                            pp.pprint(ret)

            except exceptions.LuaError as e:
                print(f"<< [LUA ERROR] {e}")
                if multiline_mode:
                    multiline_mode = False
            except KeyboardInterrupt:
                if multiline_mode:
                    multiline_mode = False
                    print("\nExited multiline mode.")
                else:
                    print("\nExiting...")
                    break
            except (socket.timeout, ConnectionResetError) as e:
                print(f"\nConnection lost: {e}", file=sys.stderr)
                break

    finally:
        # --- Cleanup ---
        lt.disconnect()
        print("Disconnected.")


if __name__ == "__main__":
    main()
