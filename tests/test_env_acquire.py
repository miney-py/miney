"""Tests for miney.env.acquire."""
import io
import zipfile
from pathlib import Path

import pytest

from miney.env.acquire import (
    acquire_luanti,
    can_acquire,
    install_instructions,
    select_asset,
)
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


def test_no_asset_exists_for_linux():
    assert select_asset(RELEASE, "Linux", "x86_64") is None


def test_can_acquire_is_false_on_linux():
    assert can_acquire("Linux") is False
    assert can_acquire("Windows") is True
    assert can_acquire("Darwin") is True


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
    assert "5.7" in install_instructions(RELEASE)


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


def test_acquire_refuses_on_linux(tmp_path: Path):
    paths = EnvPaths(root=tmp_path / ".miney")
    with pytest.raises(MineyRunError, match="flatpak"):
        acquire_luanti(paths, RELEASE, fetch=lambda url: b"", system="Linux", machine="x86_64")


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
