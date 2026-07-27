"""Tests for miney.env.acquire."""
import io
import json
import os
import zipfile
from pathlib import Path

import pytest

from miney.env import acquire
from miney.env.acquire import (
    APPIMAGE_RELEASES_URL,
    acquire_luanti,
    appimage_release,
    can_acquire,
    install_instructions,
    select_asset,
)
from miney.env.discover import MIN_VERSION_TEXT
from miney.env.paths import EnvPaths
from miney.env.upstream import Release
from miney.exceptions import MineyRunError

RELEASE = Release(
    version=(5, 16, 1),
    tag="5.16.1",
    assets={
        "luanti-5.16.1-win64.zip": "https://example.invalid/win64.zip",
        "luanti-5.16.1-win32.zip": "https://example.invalid/win32.zip",
        "luanti-5.16.1.exe": "https://example.invalid/installer.exe",
        "luanti-5.16.1-arm64-v8a.apk": "https://example.invalid/android.apk",
        "luanti_5.16.1-macos12.3_arm64.zip": "https://example.invalid/mac-arm.zip",
        "luanti_5.16.1-macos12.3_x86_64.zip": "https://example.invalid/mac-intel.zip",
    },
)

#: A release of the pkgforge AppImage build, which is where Linux downloads come from.
#: Its tag carries a build number and a timestamp after the Luanti version, and every
#: AppImage is published next to a .zsync file that must never be downloaded instead.
APPIMAGE_RELEASE = Release(
    version=(5, 16, 1),
    tag="5.16.1-1@2026-07-22_1784722284",
    assets={
        "Luanti-5.16.1-1-anylinux-x86_64.AppImage": "https://example.invalid/x86_64.AppImage",
        "Luanti-5.16.1-1-anylinux-x86_64.AppImage.zsync": "https://example.invalid/x86_64.zsync",
        "Luanti-5.16.1-1-anylinux-aarch64.AppImage": "https://example.invalid/aarch64.AppImage",
        "Luanti-5.16.1-1-anylinux-aarch64.AppImage.zsync": "https://example.invalid/aarch64.zsync",
    },
)


def test_selects_the_windows_64_bit_zip():
    assert select_asset(RELEASE, "Windows", "AMD64")[0] == "luanti-5.16.1-win64.zip"


def test_selects_the_windows_32_bit_zip_on_a_32_bit_machine():
    assert select_asset(RELEASE, "Windows", "x86")[0] == "luanti-5.16.1-win32.zip"


def test_selects_the_apple_silicon_zip():
    assert select_asset(RELEASE, "Darwin", "arm64")[0] == "luanti_5.16.1-macos12.3_arm64.zip"


def test_selects_the_intel_mac_zip():
    assert select_asset(RELEASE, "Darwin", "x86_64")[0] == "luanti_5.16.1-macos12.3_x86_64.zip"


def test_never_selects_the_system_wide_installer():
    # luanti-<v>.exe installs into Program Files. Miney touches nothing outside .miney.
    name, _ = select_asset(RELEASE, "Windows", "AMD64")
    assert not name.endswith(".exe")


def test_the_upstream_release_carries_no_asset_for_linux():
    # Luanti's own releases ship no Linux build at all - the AppImage comes from
    # elsewhere, so nothing in an upstream release may be mistaken for one.
    assert select_asset(RELEASE, "Linux", "x86_64") is None


def test_selects_the_x86_64_appimage():
    name, url = select_asset(APPIMAGE_RELEASE, "Linux", "x86_64")
    assert name == "Luanti-5.16.1-1-anylinux-x86_64.AppImage"
    assert url == "https://example.invalid/x86_64.AppImage"


def test_selects_the_aarch64_appimage():
    assert (
        select_asset(APPIMAGE_RELEASE, "Linux", "aarch64")[0]
        == "Luanti-5.16.1-1-anylinux-aarch64.AppImage"
    )


def test_never_selects_the_zsync_file_next_to_an_appimage():
    # Every AppImage is published alongside a .zsync of the same name, and it sorts
    # first. Downloading it would leave a few hundred KB of update metadata where the
    # program should be.
    name, _ = select_asset(APPIMAGE_RELEASE, "Linux", "x86_64")
    assert name.endswith(".AppImage")


def test_no_appimage_exists_for_an_unusual_linux_architecture():
    assert select_asset(APPIMAGE_RELEASE, "Linux", "riscv64") is None


def test_can_acquire_on_linux_depends_on_the_architecture():
    assert can_acquire("Linux", "x86_64") is True
    assert can_acquire("Linux", "aarch64") is True
    assert can_acquire("Linux", "riscv64") is False


def test_can_acquire_on_windows_and_macos():
    assert can_acquire("Windows", "AMD64") is True
    assert can_acquire("Darwin", "arm64") is True


def test_instructions_name_the_current_version_when_it_is_known():
    text = install_instructions(RELEASE)
    assert "5.16.1" in text
    assert "flatpak install flathub org.luanti.luanti" in text
    assert "uv run miney start" in text


def test_instructions_still_work_without_a_version():
    # No network means no release, and the instructions still have to be printable.
    text = install_instructions(None)
    assert "flatpak install flathub org.luanti.luanti" in text
    assert "5.16.1" not in text


def test_instructions_warn_that_a_distribution_package_may_be_too_old():
    # Read from MIN_VERSION rather than spelled out, so raising the floor does not
    # leave the message quietly naming the old one.
    assert MIN_VERSION_TEXT in install_instructions(RELEASE)


def _luanti_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("bin/luanti.exe", "binary")
        archive.writestr("builtin/init.lua", "-- lua")
    return buffer.getvalue()


def test_acquire_unpacks_into_the_environment(tmp_path: Path):
    paths = EnvPaths(root=tmp_path / ".miney")
    requested = []

    def fetch(url: str) -> bytes:
        requested.append(url)
        return _luanti_zip()

    result = acquire_luanti(paths, RELEASE, fetch=fetch, system="Windows", machine="AMD64")
    assert result == paths.luanti_dir
    assert (paths.luanti_dir / "bin" / "luanti.exe").is_file()
    assert requested == ["https://example.invalid/win64.zip"]


def test_acquire_flattens_an_archive_with_a_wrapping_directory(tmp_path: Path):
    # The real win64 ZIP wraps everything in luanti-<version>-win64/, and discover looks
    # for .miney/luanti/bin/luanti.exe - one level, not two.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("luanti-5.16.1-win64/bin/luanti.exe", "binary")
        archive.writestr("luanti-5.16.1-win64/builtin/init.lua", "-- lua")
    paths = EnvPaths(root=tmp_path / ".miney")

    acquire_luanti(paths, RELEASE, fetch=lambda url: buffer.getvalue(),
                   system="Windows", machine="AMD64")
    assert (paths.luanti_dir / "bin" / "luanti.exe").is_file()
    assert not (paths.luanti_dir / "luanti-5.16.1-win64").exists()


def test_acquire_keeps_a_macos_app_bundle_intact(tmp_path: Path):
    # The macOS ZIP's sole top-level entry is luanti.app/. It is the payload, not a
    # wrapper: flattening it would move Contents up a level and dismantle the bundle,
    # leaving something discover cannot find.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("luanti.app/Contents/MacOS/luanti", "binary")
        archive.writestr("luanti.app/Contents/Info.plist", "<plist/>")
    paths = EnvPaths(root=tmp_path / ".miney")

    acquire_luanti(paths, RELEASE, fetch=lambda url: buffer.getvalue(),
                   system="Darwin", machine="arm64")

    binary = paths.luanti_dir / "luanti.app" / "Contents" / "MacOS" / "luanti"
    assert binary.is_file()
    assert not (paths.luanti_dir / "Contents").exists()


def test_acquire_refuses_on_a_linux_architecture_with_no_appimage(tmp_path: Path):
    # pkgforge builds x86_64 and aarch64. Everyone else installs Luanti themselves, and
    # is told how rather than being left with a failed download.
    paths = EnvPaths(root=tmp_path / ".miney")
    with pytest.raises(MineyRunError, match="flatpak"):
        acquire_luanti(
            paths, RELEASE, fetch=lambda url: b"", system="Linux", machine="riscv64"
        )


def test_acquire_keeps_the_existing_install_when_the_download_is_not_a_zip(tmp_path: Path):
    # A corrupted download, a truncated transfer, or an HTML error page returned with a
    # 200 status must not cost the user a previously working installation.
    paths = EnvPaths(root=tmp_path / ".miney")
    (paths.luanti_dir / "bin").mkdir(parents=True)
    (paths.luanti_dir / "bin" / "luanti.exe").write_text("existing binary")

    with pytest.raises(MineyRunError, match="not a ZIP archive"):
        acquire_luanti(
            paths, RELEASE, fetch=lambda url: b"not a zip file at all",
            system="Windows", machine="AMD64",
        )

    assert (paths.luanti_dir / "bin" / "luanti.exe").read_text() == "existing binary"
    assert not paths.luanti_dir.with_name(paths.luanti_dir.name + ".new").exists()


# --- Linux: the AppImage ----------------------------------------------------------

#: An ELF header, which is what the ELF check in acquire looks at. The rest of a real
#: AppImage is a filesystem image no test has any use for.
FAKE_APPIMAGE = b"\x7fELF" + b"\x00" * 64


def _appimage_release_payload() -> bytes:
    return json.dumps(
        {
            "tag_name": APPIMAGE_RELEASE.tag,
            "assets": [
                {"name": name, "browser_download_url": url}
                for name, url in APPIMAGE_RELEASE.assets.items()
            ],
        }
    ).encode("utf-8")


def test_appimage_release_reads_the_version_out_of_a_pkgforge_tag():
    # The tag is "5.16.1-1@2026-07-22_1784722284" - a Luanti version, a build number and
    # a timestamp. Only the version in front of it is ours to read.
    release = appimage_release(fetch=lambda url: _appimage_release_payload())
    assert release.version == (5, 16, 1)
    assert release.tag == "5.16.1-1@2026-07-22_1784722284"


def _fake_extractor(seen: list[Path] | None = None):
    """
    An extractor that produces the tree a real ``--appimage-extract`` would.

    Anything a test wants to know about the image has to be observed here, while it is
    still on disk: acquire deletes its staging directory before returning, so a check
    made afterwards would look at a path that no longer exists and quietly pass or fail
    for the wrong reason.
    """

    def extract(image: Path, into: Path) -> Path:
        if seen is not None:
            seen.append(image)
        app_dir = into / "AppDir"
        (app_dir / "bin").mkdir(parents=True)
        (app_dir / "bin" / "luanti").write_text("binary")
        (app_dir / "share").mkdir()
        return app_dir

    return extract


def test_acquire_asks_the_appimage_repository_rather_than_the_upstream_release(
    tmp_path: Path, monkeypatch
):
    # Luanti's own releases have no Linux asset, so the release handed in by the caller
    # cannot be the one downloaded here. Taking the newest AppImage build is deliberate:
    # it is the most current Luanti actually available for Linux.
    paths = EnvPaths(root=tmp_path / ".miney")
    monkeypatch.setattr(acquire, "_extract_appimage", _fake_extractor())
    requested = []

    def fetch(url: str) -> bytes:
        requested.append(url)
        return _appimage_release_payload() if url == APPIMAGE_RELEASES_URL else FAKE_APPIMAGE

    acquire_luanti(paths, RELEASE, fetch=fetch, system="Linux", machine="x86_64")
    assert requested == [APPIMAGE_RELEASES_URL, "https://example.invalid/x86_64.AppImage"]


def test_acquire_installs_the_appimage_as_an_ordinary_luanti_tree(
    tmp_path: Path, monkeypatch
):
    # Extracted once rather than run as an AppImage: a bundled AppImage re-unpacks
    # itself on every launch, which costs seconds per "luanti --version" and would run
    # the image's own self-updater behind the user's back.
    paths = EnvPaths(root=tmp_path / ".miney")
    monkeypatch.setattr(acquire, "_extract_appimage", _fake_extractor())

    result = acquire_luanti(
        paths,
        RELEASE,
        fetch=lambda url: (
            _appimage_release_payload() if url == APPIMAGE_RELEASES_URL else FAKE_APPIMAGE
        ),
        system="Linux",
        machine="x86_64",
    )

    assert result == paths.luanti_dir
    assert (paths.luanti_dir / "bin" / "luanti").is_file()
    assert (paths.luanti_dir / "share").is_dir()
    assert not (paths.luanti_dir / "AppDir").exists()


def test_acquire_leaves_no_appimage_and_no_staging_behind(tmp_path: Path, monkeypatch):
    # The downloaded image is 40 MB of the same 133 MB that was just extracted from it.
    paths = EnvPaths(root=tmp_path / ".miney")
    monkeypatch.setattr(acquire, "_extract_appimage", _fake_extractor())

    acquire_luanti(
        paths,
        RELEASE,
        fetch=lambda url: (
            _appimage_release_payload() if url == APPIMAGE_RELEASES_URL else FAKE_APPIMAGE
        ),
        system="Linux",
        machine="x86_64",
    )

    assert not paths.luanti_dir.with_name(paths.luanti_dir.name + ".new").exists()
    assert list(paths.luanti_dir.glob("*.AppImage")) == []


@pytest.mark.skipif(os.name == "nt", reason="file modes are a POSIX concept")
def test_acquire_makes_the_downloaded_appimage_executable_before_extracting(
    tmp_path: Path, monkeypatch
):
    # It has to run itself to unpack itself, and a downloaded file is not executable.
    # Observed while the extractor runs, because acquire deletes the image afterwards.
    paths = EnvPaths(root=tmp_path / ".miney")
    executable: list[bool] = []

    def extract(image: Path, into: Path) -> Path:
        executable.append(os.access(image, os.X_OK))
        return _fake_extractor()(image, into)

    monkeypatch.setattr(acquire, "_extract_appimage", extract)

    acquire_luanti(
        paths,
        RELEASE,
        fetch=lambda url: (
            _appimage_release_payload() if url == APPIMAGE_RELEASES_URL else FAKE_APPIMAGE
        ),
        system="Linux",
        machine="x86_64",
    )

    assert executable == [True]


def test_acquire_keeps_the_existing_install_when_the_download_is_not_a_program(
    tmp_path: Path, monkeypatch
):
    # A captive portal, a rate-limit page or a truncated transfer all arrive as bytes
    # with a 200 status. Writing them over a working Luanti and only finding out at the
    # next start is the failure this prevents.
    paths = EnvPaths(root=tmp_path / ".miney")
    (paths.luanti_dir / "bin").mkdir(parents=True)
    (paths.luanti_dir / "bin" / "luanti").write_text("existing binary")
    monkeypatch.setattr(acquire, "_extract_appimage", _fake_extractor())

    with pytest.raises(MineyRunError, match="not a Linux program"):
        acquire_luanti(
            paths,
            RELEASE,
            fetch=lambda url: (
                _appimage_release_payload()
                if url == APPIMAGE_RELEASES_URL
                else b"<html>429 Too Many Requests</html>"
            ),
            system="Linux",
            machine="x86_64",
        )

    assert (paths.luanti_dir / "bin" / "luanti").read_text() == "existing binary"
    assert not paths.luanti_dir.with_name(paths.luanti_dir.name + ".new").exists()


def test_acquire_keeps_the_existing_install_when_extraction_fails(
    tmp_path: Path, monkeypatch
):
    paths = EnvPaths(root=tmp_path / ".miney")
    (paths.luanti_dir / "bin").mkdir(parents=True)
    (paths.luanti_dir / "bin" / "luanti").write_text("existing binary")

    def explode(image: Path, into: Path) -> Path:
        raise MineyRunError("Could not unpack the Luanti download.")

    monkeypatch.setattr(acquire, "_extract_appimage", explode)

    with pytest.raises(MineyRunError, match="unpack"):
        acquire_luanti(
            paths,
            RELEASE,
            fetch=lambda url: (
                _appimage_release_payload() if url == APPIMAGE_RELEASES_URL else FAKE_APPIMAGE
            ),
            system="Linux",
            machine="x86_64",
        )

    assert (paths.luanti_dir / "bin" / "luanti").read_text() == "existing binary"
    assert not paths.luanti_dir.with_name(paths.luanti_dir.name + ".new").exists()


def test_acquire_reports_an_appimage_that_unpacked_without_a_luanti_in_it(
    tmp_path: Path, monkeypatch
):
    # discover() looks for bin/luanti and nothing else. An extracted tree without one is
    # a silent "downloaded, but nothing runs" unless it is caught here.
    paths = EnvPaths(root=tmp_path / ".miney")

    def empty(image: Path, into: Path) -> Path:
        app_dir = into / "AppDir"
        app_dir.mkdir(parents=True)
        return app_dir

    monkeypatch.setattr(acquire, "_extract_appimage", empty)

    with pytest.raises(MineyRunError, match="bin/luanti"):
        acquire_luanti(
            paths,
            RELEASE,
            fetch=lambda url: (
                _appimage_release_payload() if url == APPIMAGE_RELEASES_URL else FAKE_APPIMAGE
            ),
            system="Linux",
            machine="x86_64",
        )

    assert not paths.luanti_dir.with_name(paths.luanti_dir.name + ".new").exists()


# --- replacing an installed Luanti ----------------------------------------------


def _install(root, files):
    """Write a fake Luanti install: {"relative/path": "contents"}."""
    for name, contents in files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contents, encoding="utf-8")
    return root


def test_swap_in_keeps_games_worlds_and_settings(tmp_path):
    paths = EnvPaths(root=tmp_path / ".miney", luanti_dir=tmp_path / "Luanti")
    _install(paths.luanti_dir, {
        "bin/luanti.exe": "old engine",
        "builtin/gone_in_the_new_one.lua": "orphan",
        "games/minetest_game/game.conf": "downloaded by miney",
        "worlds/handmade/world.mt": "made by hand in luanti itself",
        "textures/mypack/dirt.png": "a texture pack",
        "minetest.conf": "the user's settings",
    })
    staging = _install(tmp_path / "Luanti.new", {
        "bin/luanti.exe": "new engine",
        "games/devtest/game.conf": "ships with luanti",
        "textures/base/pack/dirt.png": "ships with luanti",
    })

    acquire.swap_in(paths, staging)

    luanti = paths.luanti_dir
    assert (luanti / "bin/luanti.exe").read_text() == "new engine"
    # The user's own things survive...
    assert (luanti / "games/minetest_game/game.conf").is_file()
    assert (luanti / "worlds/handmade/world.mt").is_file()
    assert (luanti / "textures/mypack/dirt.png").is_file()
    assert (luanti / "minetest.conf").read_text() == "the user's settings"
    # ... and what the new version brought stays next to them.
    assert (luanti / "games/devtest/game.conf").is_file()
    assert (luanti / "textures/base/pack/dirt.png").is_file()
    # An engine file the new version dropped must not creep back in.
    assert not (luanti / "builtin/gone_in_the_new_one.lua").exists()
    assert not staging.exists()
    assert not luanti.with_name("Luanti.old").exists()


def test_swap_in_does_not_overwrite_what_the_new_version_brings(tmp_path):
    paths = EnvPaths(root=tmp_path / ".miney", luanti_dir=tmp_path / "Luanti")
    _install(paths.luanti_dir, {"games/devtest/game.conf": "old devtest"})
    staging = _install(tmp_path / "Luanti.new", {"games/devtest/game.conf": "new devtest"})

    acquire.swap_in(paths, staging)

    assert (paths.luanti_dir / "games/devtest/game.conf").read_text() == "new devtest"


def test_swap_in_installs_into_an_empty_place(tmp_path):
    paths = EnvPaths(root=tmp_path / ".miney", luanti_dir=tmp_path / "Luanti")
    staging = _install(tmp_path / "Luanti.new", {"bin/luanti": "engine"})

    acquire.swap_in(paths, staging)

    assert (paths.luanti_dir / "bin/luanti").read_text() == "engine"


def test_swap_in_changes_nothing_when_the_old_install_cannot_be_moved(
    tmp_path, monkeypatch
):
    """
    The failure that matters: Luanti is still running. Renaming fails before anything
    has been removed, which is the whole point of renaming rather than deleting - a
    delete works file by file and can leave a half-removed install behind.
    """
    paths = EnvPaths(root=tmp_path / ".miney", luanti_dir=tmp_path / "Luanti")
    _install(paths.luanti_dir, {"bin/luanti.exe": "old engine", "games/mg/game.conf": "g"})
    staging = _install(tmp_path / "Luanti.new", {"bin/luanti.exe": "new engine"})

    def refuse(self, target):
        raise PermissionError("the file is in use by another process")

    monkeypatch.setattr(Path, "rename", refuse)

    with pytest.raises(MineyRunError) as error:
        acquire.swap_in(paths, staging)

    assert "miney stop" in str(error.value)
    # Untouched means untouched: the engine and the games are all still where they were.
    assert (paths.luanti_dir / "bin/luanti.exe").read_text() == "old engine"
    assert (paths.luanti_dir / "games/mg/game.conf").is_file()
