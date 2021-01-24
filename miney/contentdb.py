import urllib.request
import urllib.error
import json
import io
from typing import Union, BinaryIO
from miney import exceptions


class ContentDB:
    """
    A Library to use the minetest ContentDB.

    Documentation: https://content.minetest.net/help/api/
    """
    def _query(self, path: str = ""):
        try:
            return json.loads(urllib.request.urlopen("https://content.minetest.net/api/" + path).read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise Error404("404 - Not found")

    def packages(self, **kwargs) -> dict:
        """
        For parameters look here:
        https://content.minetest.net/help/api/#package-queries

        :return: Dict with package informations
        """
        url = "packages/?"
        for arg in kwargs:
            url += f"{arg}={kwargs[arg]}&"

        return self._query(url)

    def package(self, username: str, package: str):
        try:
            return self._query(f"packages/{username}/{package}/")
        except Error404:
            raise exceptions.ContentDBError("Package couldn't be found")

    def package_dependencies(self, username: str, package: str):
        try:
            return self._query(f"packages/{username}/{package}/dependencies/")
        except Error404:
            raise exceptions.ContentDBError("Package couldn't be found")

    def download_package(self, username: str, package: str, file: Union[str, BinaryIO] = None):
        if not file:
            file = f"{package}.zip"
        pack = self.package(username, package)
        url = None

        # workaround for http 300 redirect
        try:
            req = urllib.request.urlopen(pack["url"])
        except urllib.error.HTTPError as e:
            for header in str(e.headers).split("\n"):
                if header.lower()[:9] == "location:":
                    url = header.split(" ")[1]
                    break
        if url:
            if isinstance(file, io.BytesIO):
                file.write(urllib.request.urlopen(url).read())
            elif isinstance(file, str):
                with open(file, "wb") as f:
                    f.write(urllib.request.urlopen(url).read())

    def topics(self, **kwargs) -> dict:
        """
        For parameters look here:
        https://content.minetest.net/help/api/#topic-queries

        :return: Dict with topic informations
        """
        url = "topics/?"
        for arg in kwargs:
            url += f"{arg}={kwargs[arg]}&"

        return self._query(url)
    
    def tags(self):
        return self._query("tags/")


class Error404(Exception):
    """
    Errors 404 from contentDB.
    """
    pass
