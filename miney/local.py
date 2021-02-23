"""
Manage local minetest installations
"""
import platform
import shutil
from pathlib import Path
import os
import subprocess
import logging
import tempfile
from zipfile import ZipFile
# import miney
from .contentdb import ContentDB
from .exceptions import MinetestRunError


logger = logging.getLogger(__name__)
protocol_versions = {"5.3": 39, "5.2": 39, "5.1": 38, "5.0": 37, "0.4.17": 32, "0.4.16": 32, "0.4.15": 28}


class System:
    """
    Manage a local minetest installation
    """
    def __init__(self, path: str = None):
        # discoverable information
        self.build_type = None
        self.executable = None
        self.games_dir = None
        self.irrlicht = None
        self.is_snap = False
        self.mods_dir = None
        self.protocol_version = None
        self.run_in_place = None
        self.share_dir = None
        self.static_localedir = None
        self.static_sharedir = None
        self.texture_dir = None
        self.use_curl = None
        self.use_freetype = None
        self.use_gettext = None
        self.use_luajit = None
        self.use_sound = None
        self.user_dir = None
        self.version = None
        self.worlds_dir = None

        self.discover_minetest(path)
        self.contentdb = ContentDB()

    @staticmethod
    def discover_minetest(self, path: str = None) -> None:
        """
        Find a minetest installation or portable version and get all relevant information about.
        :param path: Give a path to look first for minetest
        """

        minetest = None
        if shutil.which("minetest"):  # is minetest in path?
            minetest = shutil.which("minetest")
        else:
            locations = [
                path,
                os.getcwd(),
                os.path.join(Path.home(), "Minetest", "bin"),
                os.path.join(os.getcwd(), "Minetest", "bin"),
                os.path.join(os.getcwd(), "..", "Minetest", "bin"),
            ]
            if platform.system() == 'Windows':
                locations.append(os.path.join(os.environ["PROGRAMFILES"], "Minetest", "bin"))
                locations.append(os.path.join(os.environ["PROGRAMFILES(X86)"], "Minetest", "bin"))
            if platform.system() == 'Linux':
                locations.append(os.path.join(Path.home(), "minetest", "bin"))
                locations.append(os.path.join(os.getcwd(), "minetest", "bin"))
                locations.append(os.path.join("/", "usr", "local"))
                locations.append(os.path.join("/", "usr", "bin"))

            for localtion in locations:
                minetest = shutil.which("minetest", path=localtion)
                if minetest:
                    break

        if not minetest:
            raise MinetestRunError(f"Couldn't find minetest executable.")

        try:
            result = subprocess.Popen([minetest, "--version"], shell=False, stdout=subprocess.PIPE)
        except FileNotFoundError as e:
            raise MinetestRunError(f"Couldn't run minetest binary from {minetest}")
        infos = self.__dict__
        for line in result.stdout.readlines():  # read and store result in log file
            if line:
                line = line.decode().strip()
                if line[:8] == "Minetest":
                    infos["version"] = line.split(" ", maxsplit=1)[1]
                    continue
                if line[:14] == "Using Irrlicht":
                    infos["irrlicht"] = line.split(" ", maxsplit=2)[2]
                    continue
                line = line.split("=")
                if line[1] == "0":
                    infos[line[0].lower()] = False
                elif line[1] == "1":
                    infos[line[0].lower()] = True
                else:
                    infos[line[0].lower()] = line[1].replace("\"", "")
        if not infos:
            raise MinetestRunError("Couldn't get minetest paths.")

        infos["executable"] = minetest
        infos["bin_dir"] = os.path.dirname(minetest)

        if infos["run_in_place"]:  # portable
            infos["share_dir"] = os.path.abspath(os.path.join(os.path.dirname(minetest), ".."))
            infos["user_dir"] = os.path.abspath(os.path.join(os.path.dirname(minetest), ".."))
        else:  # installed
            if platform.system() == 'Windows':
                infos["share_dir"] = os.path.abspath(os.path.join(os.path.dirname(minetest), ".."))
                infos["user_dir"] = os.path.abspath(os.path.join(os.getenv('APPDATA'), "Minetest"))
            if platform.system() == 'Linux':
                infos["share_dir"] = infos["static_sharedir"]
                if minetest[:6] == "/snap/":  # Installed with snap
                    infos["user_dir"] = os.path.abspath(os.path.join("~", "snap", "minetest", "current"))
                    self.is_snap = True
                else:
                    infos["user_dir"] = os.path.abspath(os.path.join("~", ".minetest"))
        self.mods_dir = os.path.join(self.user_dir, "mods")
        self.games_dir = os.path.join(self.user_dir, "games")
        self.worlds_dir = os.path.join(self.user_dir, "worlds")
        self.texture_dir = os.path.join(self.user_dir, "textures")

        # find protocol version
        if self.version[:1] == "5":
            if self.version[:3] in protocol_versions:
                self.protocol_version = protocol_versions[self.version[:3]]
        elif self.version[:3] == "0.4":
            if self.version[:6] in protocol_versions:
                self.protocol_version = protocol_versions[self.version[:6]]
            else:
                logger.warning("Detected unknown or to old minetest 0.4 version")
        else:
            self.protocol_version = 39  # We just set to latest known version
            logger.warning("Detected unsupported version, there could be problems with mod and game installation.")

    def install_package(self, username: str, package: str, with_dependencies: bool = False, with_optional_dependencies: bool = False) -> False:
        """
        Automatically install a package to the correct folder. It can also automatically install dependency mods.

        :param username: The username of the package creator
        :param package: The package name
        :param with_dependencies: Set to True to install with dependencies
        :param with_optional_dependencies: Set to True to install with optional dependencies
        """

        # Does it exists? Is it mod or game?
        type_ = self.contentdb.package(username, package)["type"]
        if type_ == "mod":
            install_dir = self.mods_dir
            conf_file = "mod.conf"
        elif type_ == "game":
            install_dir = self.games_dir
            conf_file = "game.conf"
        elif type_ == "txp":
            install_dir = self.texture_dir
            conf_file = "texture_pack.conf"
        else:
            raise InstallationException("Couldn't detect package type.")

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                os.mkdir(os.path.join(install_dir, package))
            except FileExistsError:
                pass

            self.contentdb.download_package(username, package, os.path.join(tmpdir, package + ".zip"))

            with ZipFile(os.path.join(tmpdir, package + ".zip"), 'r') as zipObj:
                pack_folder = os.path.join(install_dir, package)
                zipObj.extractall(pack_folder)

                # some may be in subfolders, we need to fix this
                if conf_file not in zipObj.namelist():
                    logger.debug(f"Fixing filepaths for {package}")
                    # find subfolder name
                    for file in zipObj.namelist():
                        if conf_file in file:
                            folder = file[:-(len(conf_file) + 1)]  # extract folder path
                            break
                    # move files
                    for file in os.listdir(os.path.join(pack_folder, folder)):
                        if os.path.isdir(os.path.join(pack_folder, file)):
                            shutil.rmtree(os.path.join(pack_folder, file))
                        else:
                            try:
                                os.remove(os.path.join(pack_folder, file))
                            except FileNotFoundError:
                                pass
                        shutil.move(os.path.join(pack_folder, folder, file), os.path.join(pack_folder, file))
                    shutil.rmtree(os.path.join(pack_folder, folder))

                logger.info(f"Installed '{package}' to '{os.path.join(install_dir, package)}'.")

        if with_dependencies or with_optional_dependencies:
            dependencies = self.contentdb.package_dependencies(username, package)[username + "/" + package]

            for dep in dependencies:
                if dep['name'] != "default":
                    logger.debug(f"Looking for dependency '{dep['name']}'")
                    for pack in dep["packages"]:
                        usr = pack.split("/")[0]
                        packname = pack.split("/")[1]
                        if packname == dep['name']:
                            if not dep['is_optional'] and dep['name'] != "default":
                                logger.debug(f"Found dependency '{dep['name']}' for '{package}': {pack}")
                                self.install_package(usr, packname, with_dependencies=True)
                            if with_optional_dependencies and dep['is_optional'] and dep['name'] != "default":
                                logger.debug(f"Found optional dependency '{dep['name']}' for '{package}': {pack}")
                                self.install_package(usr, packname, with_optional_dependencies=True)

    def remove_mod(self, package: str) -> None:
        """
        Remove a mod.

        :param package: Name of the mod to remove
        """
        shutil.rmtree(os.path.join(self.mods_dir, package))


class InstallationException(Exception):
    pass