import sys
import os
import socket

try:
    from miney import Minetest, exceptions
except ModuleNotFoundError:
    sys.path.append(os.getcwd())
    from miney import Minetest, exceptions

server = sys.argv[1] if 1 < len(sys.argv) else "127.0.0.1"
port = sys.argv[2] if 2 < len(sys.argv) else 29999
playername = sys.argv[3] if 3 < len(sys.argv) else "Player"
password = sys.argv[4] if 4 < len(sys.argv) else ""

mt = Minetest(server, playername, password, port)

print("python luaconsole.py [<server> <port> <playername> <password>] - All parameter optional on localhost")
print("Press ctrl+c to quit. Start multiline mode with \"--\", run it with two empty lines, exit it with ctrl+c")

multiline_mode = False
multiline_cmd = ""
ret = ""

while True:
    if mt.event_queue:
        print(mt.event_queue)
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
                    ret = mt.lua.run(multiline_cmd)
                    multiline_mode = False
                    if not isinstance(ret, type(None)):  # print everything but none
                        print("<<", ret)
            else:
                ret = mt.lua.run(cmd)

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
