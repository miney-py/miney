"""
How to replace the installed Miney with a newer one.

Deciding *how* to upgrade is separate from running it, and both are separate from
asking the user - the command line does the asking. The decision is one function, so
that it can be shown ("that is the same as running ...") before anything happens.

Only the Lua mod's Python half is upgraded here. The mod itself needs no step of its
own: it ships inside the wheel, and ``manage._refresh_mod`` copies it into a world on
the next ``miney start``.
"""
from __future__ import annotations

import importlib.util
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ..exceptions import MineyRunError

logger = logging.getLogger(__name__)

#: The name on PyPI.
PACKAGE = "miney"


#: Why a Windows user has to run the upgrade themselves. Windows refuses to delete an
#: executable that is running, and ``miney upgrade`` runs as ``miney.exe`` - the very
#: file the upgrade replaces. ``uv`` deletes it and stops with "Access denied"; typed
#: into a terminal by hand the same command works, because then no miney.exe is running.
WINDOWS_MANUAL = (
    "Windows cannot replace miney.exe while it is running, and that is the file this "
    "upgrade replaces.\nSo please run that command yourself - copy the line above into "
    "your terminal."
)


@dataclass(frozen=True)
class Plan:
    """
    What ``miney upgrade`` would do.

    :param command: The command that performs the upgrade, empty when there is none.
    :param refusal: Why no upgrade is possible, already phrased for the user, or None
        when there is a command.
    :param manual: Why the command has to be typed by the user rather than run by
        Miney, already phrased, or None when Miney can run it itself.
    """

    command: list[str]
    refusal: str | None = None
    manual: str | None = None

    @property
    def shown(self) -> str:
        """
        The command as a line a user could type themselves.

        :return: The command, space-joined.
        """
        return " ".join(self.command)

    @property
    def runnable(self) -> bool:
        """
        Whether Miney may run this command itself.

        :return: True when there is a command and nothing stands in the way of running
            it here.
        """
        return self.refusal is None and self.manual is None


def source_checkout() -> Path | None:
    """
    The source tree this Miney is being run from, if it is one.

    An editable install and a plain checkout both put a ``pyproject.toml`` next to the
    package directory; a wheel installed into ``site-packages`` never does. Upgrading
    from PyPI would either fail or silently shadow the code the user is editing, so
    this is what makes ``upgrade`` refuse instead.

    :return: The repository root, or None when Miney was installed normally.
    """
    root = Path(__file__).resolve().parent.parent.parent
    return root if (root / "pyproject.toml").is_file() else None


def has_pip() -> bool:
    """
    Whether pip is importable from the interpreter Miney runs on.

    A venv made by ``uv venv`` - the way the documentation creates one - has no pip in
    it, so this is genuinely often False.

    :return: True when ``python -m pip`` would work here.
    """
    try:
        return importlib.util.find_spec("pip") is not None
    except (ImportError, ValueError):
        return False


def pip_needed_here() -> bool:
    """
    Whether this environment should be given pip so that it can upgrade Miney later.

    Only Windows needs it. There the upgrade replaces the running ``miney.exe``, and
    only pip survives that, so a venv from ``uv venv`` - which has no pip - would leave
    ``miney upgrade`` unable to do more than print a command. Everywhere else ``uv``
    does the job, and installing pip would be 2 MB nobody asked for.

    Never true for a source checkout: a developer's environment is theirs, and
    ``git pull`` updates it anyway.

    :return: True when :func:`install_pip` is worth running here.
    """
    if sys.platform != "win32":
        return False
    return not has_pip() and source_checkout() is None


def install_pip() -> str | None:
    """
    Put pip into the environment Miney runs in, so it can upgrade itself later.

    ``ensurepip`` rather than ``uv pip install pip``: it is part of the standard
    library, needs no network and no uv, and installs the wheel that ships with the
    interpreter. A venv made by ``uv venv`` has no pip, which is precisely the case
    where ``miney upgrade`` would otherwise be unable to do its job on Windows.

    Never raises. pip is a convenience for a later upgrade, so failing to get it must
    not stop the world that is being set up.

    :return: None on success, or a message describing why pip could not be installed.
    """
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "ensurepip", "--upgrade"],
            capture_output=True,
            text=True,
        )
    except OSError as error:
        return f"Could not run ensurepip: {error}"
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        return f"ensurepip failed: {detail[-1] if detail else 'no output'}"
    return None


def plan() -> Plan:
    """
    Decide how to upgrade this installation.

    pip comes first, and not for taste: on Windows the upgrade replaces the very
    ``miney.exe`` that is running it, and only pip survives that. It moves the file
    aside, which Windows allows for a running executable, while ``uv`` deletes it and
    stops with "Access denied". Where pip is missing - a plain ``uv venv`` has none -
    ``uv`` takes over, and on Windows that plan is shown rather than run.

    The interpreter is always named explicitly, so the venv that gets upgraded is the
    one the running ``miney`` command came from, not whatever ``VIRTUAL_ENV`` points at.

    :return: The plan. Check :attr:`Plan.runnable` before running the command.
    """
    checkout = source_checkout()
    if checkout is not None:
        return Plan(
            command=[],
            refusal=(
                f"You are running Miney from its source code at {checkout}, not from an "
                "installed package, so there is nothing for pip to upgrade.\n"
                "Get the newest code with:\n"
                "  git pull"
            ),
        )

    if has_pip():
        # --disable-pip-version-check: the pip that ensurepip brings along is a little
        # behind, and its "a new release of pip is available" notice is noise a learner
        # would read as something they now have to do.
        return Plan([
            sys.executable, "-m", "pip", "install", "--upgrade", PACKAGE,
            "--disable-pip-version-check",
        ])

    if shutil.which("uv") is None:
        return Plan(
            command=[],
            refusal=(
                "Neither uv nor pip is available here, so there is no way to upgrade "
                "Miney from inside it.\n"
                "Install uv - it is what the Miney documentation uses - and try again:\n"
                "  https://docs.astral.sh/uv/getting-started/installation/"
            ),
        )

    command = ["uv", "pip", "install", "--upgrade", PACKAGE, "--python", sys.executable]
    if sys.platform == "win32":
        return Plan(command, manual=WINDOWS_MANUAL)
    return Plan(command)


def run(plan_to_run: Plan) -> None:
    """
    Perform the upgrade.

    The installer's own output goes straight to the terminal: it names what it
    downloaded and which version arrived, which is exactly what a learner wants to see.

    :param plan_to_run: A plan whose ``refusal`` is None.
    :raises MineyRunError: If the installer could not be started or failed. Windows
        cannot overwrite a running executable, and ``miney upgrade`` runs as one, so
        the message always carries the command to run by hand.
    """
    try:
        completed = subprocess.run(plan_to_run.command)
    except OSError as error:
        raise MineyRunError(
            f"Could not start the upgrade: {error}\n"
            f"Run it yourself with:\n  {plan_to_run.shown}"
        ) from error
    if completed.returncode != 0:
        raise MineyRunError(
            "The upgrade did not finish.\n"
            f"Run it yourself to see why:\n  {plan_to_run.shown}"
        )
