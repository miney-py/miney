import sys
import os
import socket

try:
    from miney import Luanti, exceptions
except ModuleNotFoundError:
    sys.path.append(os.getcwd())
    from miney import Luanti, exceptions

server = sys.argv[1] if 1 < len(sys.argv) else "127.0.0.1"
port = int(sys.argv[2]) if 2 < len(sys.argv) else 30000
playername = sys.argv[3] if 3 < len(sys.argv) else "miney"
password = sys.argv[4] if 4 < len(sys.argv) else "ChangeThePassword!"

lt = Luanti(server, playername, password, port)

print("python luaconsole.py [<server> <port> <playername> <password>] - All parameter optional on localhost")
print("Press ctrl+c to quit. Start multiline mode with \"--\", run it with two empty lines, exit it with ctrl+c")
print("All Lua code you are sending runs inside a function block. You have to use 'return' in your lua code to return something and get it back to python.")

multiline_mode = False
multiline_cmd = ""
ret = ""

while True:
    try:
        if not multiline_mode:
            cmd = input(">> ")
            multiline_cmd = ""
        else:
            cmd = input("-- ")

        if cmd == "--":
            multiline_mode = True
        else:
            if multiline_mode:
                multiline_cmd = multiline_cmd + cmd + "\n"

                if "\n\n" in multiline_cmd:
                    ret = lt.lua.run(multiline_cmd)
                    multiline_mode = False
                    if not isinstance(ret, type(None)):  # print everything but none
                        print("<<", ret)
            else:
                ret = lt.lua.run(cmd)

                if not isinstance(ret, type(None)):  # print everything but none
                    print("<<", ret)

    except exceptions.LuaError as e:
        print("<<", e)
        if multiline_mode:
            multiline_mode = False
    except (socket.timeout, ConnectionResetError) as e:
        print(e)
        sys.exit(-1)
    except KeyboardInterrupt:
        if multiline_mode:
            multiline_mode = False
            print("")
        else:
            sys.exit()
