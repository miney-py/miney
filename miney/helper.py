import socket
import time
import os
import platform
import subprocess
import webbrowser
import miney


def is_miney_available(ip: str = "127.0.0.1", port: int = 29999, timeout: int = 1.0) -> bool:
    """
    Check if there is a running miney game available on an optional given host and/or port.
    This functions pings mineysocket and waits **timeout** seconds for a pong.

    :param ip: Optional IP or hostname
    :param port: Optional port
    :param timeout: Optional timeout
    :return: True or False
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, int(port)))
        s.send(b"ping\n")
        reply = s.recv(4096).decode()
        if reply == "pong\n":
            return True
        else:
            return False
    except (socket.timeout, ConnectionResetError, ConnectionRefusedError):
        return False
    finally:
        s.close()


def run_miney_game():
    """
    Run minetest with the miney world. Miney will look for the minetest executable in common places for itself,
    but it's also possible to provide the path as parameter or as environment variable :envvar:`MINETEST_BIN`.

    :return: None
    """
    if is_miney_available():
        raise miney.MinetestRunError("A miney game is already running")
    else:
        run_minetest(show_menu=False)
        wait = 0
        while wait < 12:
            time.sleep(1)
            available = is_miney_available()
            if available:
                time.sleep(2)  # some extra time to get everything initialized
                return True
            wait = wait + 1
        raise miney.MinetestRunError("Timeout while waiting for minetest with an open mineysocket")


def run_minetest(
        minetest_path: str = None,
        show_menu: bool = True,
        world_path: str = "Miney",
        seed: str = "746036489947438842"
) -> None:
    """
    Run minetest. Miney will look for the minetest executable in common places for itself,
    but it's also possible to provide the path as parameter or as environment variable 'MINETEST_BIN'.

    :param minetest_path: Path to the minetest executable
    :param show_menu: Start in the world or in the menu
    :param world_path: Optional world path
    :param seed: Optional world seed
    :return: None
    """
    if not minetest_path:
        if os.environ.get('MINETEST_BIN') and os.path.isfile(os.environ.get('MINETEST_BIN')):
            minetest_path = os.environ['MINETEST_BIN']
        else:
            if platform.system() == 'Windows':
                exe_name = "minetest.exe"
            else:
                exe_name = "minetest"

            # we have to guess the path
            possible_paths = [
                os.path.join(os.getcwd(), "Minetest", "bin"),
            ]
            for p in possible_paths:
                path = os.path.join(p, exe_name)
                if os.path.isfile(path):
                    minetest_path = os.path.join(p, exe_name)
                    break
                else:
                    raise miney.MinetestRunError("Minetest was not found")
    if world_path == "Miney":
        world_path = os.path.abspath(os.path.join(minetest_path, "..", "..", "worlds", "miney"))

        if not os.path.isdir(world_path):  # We have to create the default world
            if not os.path.isdir(os.path.abspath(os.path.join(world_path, "..", "..", "worlds"))):
                os.mkdir(os.path.abspath(os.path.join(world_path, "..", "..", "worlds")))
            os.mkdir(world_path)
            with open(os.path.join(world_path, "world.mt"), "w") as world_config_file:
                world_config_file.write(
                    "enable_damage = true\ncreative_mode = false\ngameid = minetest\nplayer_backend = sqlite3\n"
                    "backend = sqlite3\nauth_backend = sqlite3\nload_mod_mineysocket = true\nserver_announce = false\n"
                )
            with open(os.path.join(world_path, "map_meta.txt"), "w") as world_meta_file:
                world_meta_file.write(f"seed = {seed}")

    if not os.path.isdir(os.path.abspath(os.path.join(minetest_path, "..", "..", "mods", "mineysocket"))):
        raise miney.MinetestRunError("Mineysocket mod is not installed")

    # todo: run_minetest - implementation for linux/macos

    if show_menu:
        subprocess.Popen(
            f"{minetest_path} "
            f"--world \"{world_path}\" --name {miney.default_playername} --address \"\""
        )
    else:
        subprocess.Popen(
            f"{minetest_path} "
            f"--go --world \"{world_path}\" --name {miney.default_playername} --address \"\""
        )


def doc() -> None:
    """
    Open the documention in the webbrower. This is just a shortcut for IDLE or the python interactive console.

    :return: None
    """
    webbrowser.open("https://miney.readthedocs.io/en/latest/")