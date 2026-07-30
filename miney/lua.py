"""
This module provides an interface for executing Lua code on the Luanti server. The miney mod on the server is required for this functionality to work.
"""

import linecache
import os
import re
import logging
import sys
import uuid
import time
import textwrap
from typing import Any, NamedTuple

from .exceptions import LuaResultTimeout, LuaError, LuantiConnectionError


logger = logging.getLogger(__name__)

LUA_IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

#: The largest single request Miney will send. Mirrors ``MAX_REQUEST`` in
#: ``mod_data/miney/init.lua``: the mod refuses a longer line, so refusing it here turns
#: a silent drop into a sentence that names the problem.
#:
#: Nothing a person writes comes near it. It is there because a runaway generator
#: building Lua source in a loop should hit an error rather than a full disk.
MAX_LUA_SOURCE = 16 * 1024 * 1024

#: The oldest Lua mod this version of Miney can talk to. The mod names its own number
#: (``MOD_API`` in ``mod_data/miney/init.lua``) in its beacon and in every answer, and
#: anything lower, or a mod old enough not to say at all, is refused with an error that
#: explains how to update instead of failing later on a name the mod does not have yet.
#:
#: This is not the Miney version and does not move with a release. Raise it only
#: together with ``MOD_API``, when the two halves stop understanding each other.
REQUIRED_MOD_API = 12

#: How many commands may be in flight before Miney waits for them whether or not
#: anything needs their answer.
#:
#: Sending without waiting is what makes a loop fast, and a loop with no end would
#: otherwise queue for ever: memory here, and an ever-growing request log on the server.
#: The cost of the cap is one extra server step per this many commands, which against
#: the thousands they save is nothing.
MAX_IN_FLIGHT = 500

#: Directory of the Miney package, so a frame inside it can be told from a frame in
#: somebody's own script. Used to point an error at the line that caused it.
_MINEY_DIR = os.path.dirname(os.path.abspath(__file__))


class _Origin(NamedTuple):
    """
    Where in the user's own code a command was sent from.

    Kept for every command that was sent without waiting, because the error it may
    produce is raised much later, at whatever call happens to be the next one to wait.
    Without this the traceback points at that innocent line instead.

    Captured as three cheap fields rather than a real traceback: a loop can go through
    here a thousand times, and reading the source line is left until an error actually
    needs it.

    :param filename: The file the call was made in.
    :param lineno: The line it was on.
    :param function: The name of the function it was in.
    """

    filename: str
    lineno: int
    function: str

    def describe(self) -> str:
        """
        Name the place, with the line of source if it can still be read.

        :return: One or two lines, ready to append to an error message.
        """
        where = f'  File "{self.filename}", line {self.lineno}, in {self.function}'
        source = linecache.getline(self.filename, self.lineno).strip()
        return f"{where}\n    {source}" if source else where


def _caller_origin() -> _Origin | None:
    """
    The first frame outside Miney itself.

    Everything between the user's line and here is library plumbing - ``nodes.set``
    calling ``lua.run``, and so on - so the frames are walked until one is in a file
    that is not part of the package.

    :return: Where the call came from, or None if the whole stack is inside Miney.
    """
    frame = sys._getframe(1)
    while frame is not None:
        filename = frame.f_code.co_filename
        if not os.path.abspath(filename).startswith(_MINEY_DIR):
            return _Origin(filename, frame.f_lineno, frame.f_code.co_name)
        frame = frame.f_back
    return None


#: Lua's own escapes for the characters that have one. Everything else below a space
#: becomes a numeric escape - see :func:`_lua_string`.
_LUA_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\a": "\\a",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\v": "\\v",
}


def _lua_string(value: str) -> str:
    """
    Quote a Python string as a Lua string literal.

    Written by hand rather than with :func:`json.dumps`, which looks close enough to
    Lua but escapes control characters as ``\\u0000``. Lua has no ``\\u`` escape, so
    the server answered ``chat.send_to_all("hello\\x00world")`` with *invalid escape
    sequence* - a Lua syntax error, at somebody who never wrote any Lua.

    Control characters may not travel unescaped either. A newline inside a Lua string
    literal is a syntax error, and the request survives the trip whole: Python's
    ``json.dumps`` escapes it on the way out and the mod's ``parse_json`` puts the real
    byte back before ``loadstring`` ever sees it.

    Numeric escapes are always padded to three digits. ``"\\7"`` followed by a literal
    ``8`` would otherwise read as ``"\\78"``.

    :param value: The string to quote.
    :return: A Lua string literal, quotes included.
    """
    out = ['"']
    for character in value:
        escape = _LUA_ESCAPES.get(character)
        if escape is not None:
            out.append(escape)
        elif character < " " or character == "\x7f":
            out.append(f"\\{ord(character):03d}")
        else:
            out.append(character)
    out.append('"')
    return "".join(out)


class Lua:
    """
    Provides an interface for executing Lua code on the Luanti server.

    This functionality is dependent on the 'miney' mod being installed and running on
    the server. Reached as :attr:`~miney.Luanti.lua`, never built by hand.
    """
    def __init__(self, transport):
        #: The channel to the server. Everything below only asks it to carry a field
        #: table and to say what came back.
        self.transport = transport
        self.pending_lua_results: dict[str, dict | None] = {}
        #: Commands that were sent without waiting for their answer, in the order they
        #: went out, each with the line of user code it came from.
        self._in_flight: list[tuple[str, _Origin | None]] = []
        transport.add_listener(self._handle_answer)

    @property
    def mod_api(self) -> int | None:
        """
        Which contract version the Lua mod on the server speaks.

        None while nothing has said. Compared against ``REQUIRED_MOD_API``.
        """
        return self.transport.mod_api

    def _handle_answer(self, record: dict) -> None:
        """
        Take one answer off the transport and give it to whoever is waiting for it.

        :param record: What the mod sent, already decoded.
        """
        execution_id = record.get("execution_id")
        if not execution_id:
            # An event or an acknowledgement, not an answer to a lua.run.
            return
        if execution_id in self.pending_lua_results:
            self.pending_lua_results[execution_id] = record
            logger.debug("Stored the result for %s.", execution_id)
        else:
            logger.warning(
                "Received a Lua result for an unknown or already processed id: '%s'.",
                execution_id,
            )

    def _check_mod_api(self) -> None:
        """
        Refuse a Lua mod that is older than this version of Miney.

        Miney ships the mod it needs, so the two halves normally move together. They
        come apart when the mod was installed by hand or from ContentDB and only the
        Python side was updated. Without this check the symptom is whatever the new
        half asks for first - ``attempt to index global 'storage' (a nil value)`` -
        which reads as a bug in the user's own code.

        :raises LuantiConnectionError: If the mod is too old, or too old to say.
        """
        if self.mod_api is not None and self.mod_api >= REQUIRED_MOD_API:
            return

        found = "did not say which version it is" if self.mod_api is None \
            else f"speaks version {self.mod_api}"
        raise LuantiConnectionError(
            f"The 'miney' mod on the server is too old for this version of Miney: it "
            f"{found}, and version {REQUIRED_MOD_API} is needed. Update the mod on the "
            f"server. For a world you started with the 'miney' command, that is "
            f"'miney upgrade'; for somebody else's server, the admin updates it from "
            f"https://content.luanti.org/packages/Miney/miney/"
        )

    def run(self, lua_code: str, timeout: int = 10, execution_id: str = None,
            wait: bool = True) -> Any:
        """
        Execute Lua code on the server and return the result.

        The code runs in a sandbox that lives as long as your connection, so a global
        you assign in one call is still there in the next one::

            lt.lua.run("counter = (counter or 0) + 1")
            lt.lua.run("counter = (counter or 0) + 1")
            print(lt.lua.run("return counter"))  # 2

        The names are yours alone - another script on the same server has its own set -
        and they are gone once you disconnect. Assigning a name the sandbox already
        provides (``minetest = 5``) hides it for your connection only.

        The sandbox has no ``_G``. ``_G.counter = 1`` raises *attempt to index global
        '_G' (a nil value)* - assign the bare name instead, as above.

        .. warning::

           The sandbox keeps scripts from tripping over each other. It is not a security
           boundary. Everything Luanti gives a mod is reachable from here, so granting
           somebody the ``miney`` privilege on your server is granting them the server.

        To keep something for longer than that, write it to ``storage``, the world's own
        key-value store::

            lt.lua.run("storage:set_string('base', '10,20,30')")
            print(lt.lua.run("return storage:get_string('base')"))  # '10,20,30'

        It lives in the world directory and survives a server restart, which is also the
        trade-off: every script on that world shares one set of keys. It is Luanti's
        ``StorageRef``, so ``set_string``, ``get_string``, ``set_int``, ``get_int``,
        ``to_table`` and ``from_table`` all work.

        ``wait=False`` sends the code and returns straight away, without waiting for the
        server to run it. This is how Miney makes a loop fast - the server picks up
        everything that has arrived in one go, so a thousand commands cost one server
        step instead of a thousand - and it is what every method that has nothing to
        return already does for you. Reach for it directly only for Lua of your own that
        answers with nothing::

            for i in range(1000):
                lt.lua.run(f"minetest.log('action', 'line {i}')", wait=False)
            lt.lua.flush()      # not needed before another Miney call, which waits anyway

        The answer still comes; nobody is listening for it yet. The next call that does
        need an answer looks at it first, so an error is never lost - it is raised there
        instead, with the line it really came from named in the message.

        :param lua_code: The Lua code to execute.
        :param timeout: Maximum wait time in seconds for the result.
        :param execution_id: A unique ID for this execution. If None, one will be generated.
        :param wait: Whether to wait for the result. With ``False`` the return value is
            always None.
        :return: The result of the Lua execution. Can be None if the script returns no value.
        :raises LuaResultTimeout: When the timeout is reached.
        :raises LuantiConnectionError: When there is no connection to the server or the required 'miney' mod is missing.
        :raises LuaError: When the Lua code execution results in an error on the server.
        """
        if not lua_code or lua_code.isspace() or lua_code.strip() == "":
            logger.warning("No Lua code provided to execute.")
            return None

        # Dedent to allow for nicely formatted multiline strings
        lua_code = textwrap.dedent(lua_code)

        if not self.transport.connected:
            raise LuantiConnectionError("Not connected to the server")

        self._check_mod_api()

        # Generate a unique ID if none was provided
        if execution_id is None:
            execution_id = str(uuid.uuid4())

        source_size = len(lua_code.encode())
        if source_size > MAX_LUA_SOURCE:
            raise LuaError(
                f"This Lua code is too long to send: {source_size} bytes, and the mod "
                f"takes at most {MAX_LUA_SOURCE}. Send it in several smaller calls, "
                f"or replace a long list of values in the code with a loop that builds "
                f"it."
            )

        # Register the execution ID as pending
        self.pending_lua_results[execution_id] = None

        logger.debug(f"Sending Lua code with ID {execution_id}: {lua_code}")

        try:
            self.transport.send({
                "lua": lua_code,
                "execute": "true",
                "execution_id": execution_id,
            })
        except ValueError as e:
            logger.error(f"Failed to send Lua code: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error sending Lua code: {e}")
            return f"Error: {str(e)}"

        if not wait:
            self._in_flight.append((execution_id, _caller_origin()))
            if len(self._in_flight) >= MAX_IN_FLIGHT:
                self.flush(timeout)
            return None

        parsed_response = self._await(execution_id, timeout)

        # Everything sent earlier is answered by now: the mod runs the requests in the
        # order they arrived and answers them in that order, so an answer to this one
        # is proof that the ones before it are in. Checked first, because an error that
        # happened earlier is the one worth raising.
        self._collect_in_flight()

        return self._unpack(parsed_response)

    def flush(self, timeout: float = 10) -> None:
        """
        Wait for every command that was sent without waiting for its answer.

        Called for you: by the next command that needs an answer, and when the
        connection closes. Worth calling by hand only when a script has to know that
        the world really has caught up before it does something outside Miney - taking
        a screenshot, say, or writing a file.

        :param timeout: Seconds to wait.
        :raises LuaError: If one of those commands failed. The message names the line
            it was sent from.
        :raises LuaResultTimeout: If the server stopped answering.
        """
        if not self._in_flight:
            return
        last_id = self._in_flight[-1][0]
        self._await(last_id, timeout, keep=True)
        self._collect_in_flight()

    def _await(self, execution_id: str, timeout: float, keep: bool = False) -> dict:
        """
        Wait for one answer.

        :param execution_id: What to wait for.
        :param timeout: Seconds to wait.
        :param keep: Leave the answer in place instead of taking it, for a caller that
            reads it again afterwards.
        :return: The answer.
        :raises LuaResultTimeout: If it never came.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.pending_lua_results.get(execution_id) is not None:
                break
            time.sleep(0.001)

        if keep:
            answer = self.pending_lua_results.get(execution_id)
        else:
            answer = self.pending_lua_results.pop(execution_id, None)

        if answer is None:
            # Whatever else was on its way is now of unknown fate, and holding on to it
            # would blame the next call for this one's silence.
            self._forget_in_flight()
            raise LuaResultTimeout(
                f"The server did not answer within {timeout} seconds.\n"
                f"{self.transport.timeout_hint()}"
            )
        return answer

    def _collect_in_flight(self) -> None:
        """
        Take the answers to everything that was sent without waiting, and raise the
        first failure among them.

        :raises LuaError: If one of them failed, naming where it was sent from.
        """
        outstanding, self._in_flight = self._in_flight, []
        for execution_id, origin in outstanding:
            answer = self.pending_lua_results.pop(execution_id, None)
            if answer is None:
                # Cannot happen while the mod answers in order; not worth an exception
                # if it ever does, because the command itself did run.
                logger.debug("No answer arrived for %s.", execution_id)
                continue
            if "error" in answer:
                self._forget_in_flight()
                self._unpack(answer, origin)

    def _forget_in_flight(self) -> None:
        """Drop everything still outstanding, without waiting for it."""
        for execution_id, _ in self._in_flight:
            self.pending_lua_results.pop(execution_id, None)
        self._in_flight = []

    def _unpack(self, parsed_response: dict, origin: "_Origin | None" = None) -> Any:
        """
        Turn one answer into a return value, or into the exception it deserves.

        :param parsed_response: What the mod sent.
        :param origin: Where the command was sent from, when that is not simply the
            line the caller is standing on.
        :return: What the Lua code returned, or None if it returned nothing.
        :raises LuaError: If the Lua itself failed.
        """
        if "error" in parsed_response:
            message = parsed_response["error"]
            if origin is not None:
                # This command was sent without waiting, so Python had already moved on
                # by the time it failed and the traceback below points at whatever line
                # happened to need an answer next. Say where it really came from.
                message = (
                    f"{message}\n"
                    f"This came from a command Miney had already sent on:\n"
                    f"{origin.describe()}"
                )
            raise LuaError(message)

        if "result" in parsed_response:
            return parsed_response["result"]

        # No error and no result: the code ran and returned nothing, which is fine.
        return None

    def run_file(self, filename: str) -> Any:
        """
        Loads and runs Lua code from a file.

        This is useful for debugging, as Luanti can throw errors with
        correct line numbers. It's also easier to use with a Lua capable IDE.

        :param filename: Path to the Lua file to execute.
        :return: The result of the Lua execution.
        """
        with open(filename, "r") as f:
            return self.run(f.read())
            
    def get_node_info(self, node_name: str = None) -> Any:
        """
        Get information about a specific node or all registered nodes.

        :param node_name: The name of the node to get information about.
                          If None, returns information about all registered nodes.
        :return: The result of the Lua execution with node information.
        """
        if node_name:
            lua_code = f'return dump(minetest.registered_nodes["{node_name}"])'
        else:
            lua_code = 'local count = 0; for _ in pairs(minetest.registered_nodes) do count = count + 1 end; return {count = count, names = table.keys(minetest.registered_nodes)}'
        
        return self.run(lua_code)

    def dumps(self, data: Any) -> str:
        """
        Convert a Python data type to a string with a Lua data type.

        :param data: Python data to convert to Lua format.
        :return: Lua formatted string representation of the data.
        :raises ValueError: If the data type is not supported.
        """
        # Try to convert objects that are not base types into dicts.
        # This relies on the object implementing an iterable protocol that yields (key, value) pairs.
        if not isinstance(data, (dict, list, str, int, float, bool)) and data is not None:
            try:
                data = dict(data)
            except (TypeError, ValueError):
                # Not convertible, proceed with original data object
                pass

        if data is None:
            return "nil"
        if isinstance(data, bool):
            return "true" if data else "false"
        if isinstance(data, (int, float)):
            return str(data)
        if isinstance(data, str):
            return _lua_string(data)
        # Treat Python tuples like Lua arrays as well
        if isinstance(data, (list, tuple)):
            return "{" + ", ".join(self.dumps(item) for item in data) + "}"
        if isinstance(data, dict):
            items = []
            for k, v in data.items():
                key_str = ""
                # Check if key is a valid Lua identifier
                if isinstance(k, str) and LUA_IDENTIFIER_REGEX.match(k):
                    key_str = k
                else:
                    # If not, use ["key"] notation
                    key_str = f"[{self.dumps(k)}]"

                items.append(f"{key_str}={self.dumps(v)}")
            return "{" + ", ".join(items) + "}"

        raise ValueError(f"Unknown type {type(data)}")
        
