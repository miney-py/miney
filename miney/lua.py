"""
This module provides an interface for executing Lua code on the Luanti server. The miney mod on the server is required for this functionality to work.
"""

import re
import logging
import typing
import uuid
import time
import json
import textwrap
from typing import Any

from .exceptions import LuaResultTimeout, LuaError
from .luanticlient.exceptions import LuantiConnectionError, LuantiPermissionError
from .luanticlient.constants import ClientState
if typing.TYPE_CHECKING:
    from .luanticlient import LuantiClient


logger = logging.getLogger(__name__)

LUA_IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class Lua:
    """
    Provides an interface for executing Lua code on the Luanti server.

    This functionality is dependent on the 'miney' mod being installed and
    running on the server. The mod provides the necessary formspec
    ('miney:code_form') and server-side logic to receive, execute, and
    return results from Lua code snippets. Without this mod, any attempts
    to execute code will fail.
    """
    def __init__(self, luanti: 'LuantiClient'):
        self.luanti = luanti
        self.form_ready: bool = False
        self.pending_lua_results: dict[str, dict | None] = {}
        self._register_handlers()

    def _register_handlers(self):
        """Register miney-specific handlers with the client's command handler."""
        if self.luanti.command_handler:
            self.luanti.command_handler.register_formspec_handler(
                "miney:code_form", self._handle_miney_code_form
            )
            logger.debug("Luanti-specific handlers registered for Lua execution.")

    def _handle_miney_code_form(self, formspec: str):
        """
        Processes the `miney:code_form` response from the server.

        For this client, the formspec is a raw JSON string.

        :param formspec: The formspec string received from the server.
        """
        self.form_ready = True
        logger.debug(f"Received miney_code_form response: {formspec}")

        if formspec.startswith("formspec_version["):
            formspec = self._parse_legacy_formspec_result(formspec)
            if not formspec:
                logger.warning("Legacy formspec detected but no result JSON found; ignoring.")
                return
        try:
            # The server sends a raw JSON string as the formspec content for our client.
            response_data = json.loads(formspec)

            # The initial form call might result in a null JSON object, which is fine.
            if response_data is None:
                logger.debug("Received null JSON response. Likely an initial form. Ignoring.")
                return

            execution_id = response_data.get("execution_id")

            if not execution_id:
                logger.debug("Received formspec without an execution_id. Likely an initial form. Ignoring.")
                return

            if execution_id in self.pending_lua_results:
                # Store the entire parsed JSON object as the result
                self.pending_lua_results[execution_id] = response_data
                logger.debug(f"Stored matching Lua result for ID {execution_id}.")
            else:
                logger.warning(f"Received Lua result for unknown or already processed ID: '{execution_id}'.")
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse formspec as JSON. Content: {formspec}")
        except Exception as e:
            logger.error(f"Error processing miney_code_form response: {e}", exc_info=True)


    def _parse_legacy_formspec_result(self, formspec: str) -> str | None:
        """
        Extract JSON from the legacy formspec's 'textarea' named 'result'.
        The server now embeds the full response_data JSON here.
        Returns the result as string if found; otherwise None.
        """
        marker = ";result;"
        idx = formspec.find(marker)
        if idx == -1:
            return None
        try:
            pos_after_marker = idx + len(marker)
            # Skip the label (until next unescaped ';')
            _, pos_semicolon = self._read_until_unescaped(formspec, pos_after_marker, ';')
            # Default text starts after that semicolon, ends at next unescaped ']'
            default_raw, _ = self._read_until_unescaped(formspec, pos_semicolon + 1, ']')
            default_text = self._unescape_formspec(default_raw).strip()
            if not default_text:
                return None
            else:
                return default_text
        except Exception as e:
            logger.debug(f"Legacy formspec parse failed: {e}", exc_info=True)
            return None

    def _read_until_unescaped(self, text: str, start: int, end_char: str) -> tuple[str, int]:
        """
        Read from 'start' until the next unescaped 'end_char'.
        Returns (substring, index_of_end_char).
        """
        i = start
        buf: list[str] = []
        while i < len(text):
            ch = text[i]
            if ch == end_char:
                bs = 0
                j = i - 1
                while j >= 0 and text[j] == '\\':
                    bs += 1
                    j -= 1
                if bs % 2 == 0:
                    return "".join(buf), i
            buf.append(ch)
            i += 1
        return "".join(buf), i

    def _unescape_formspec(self, s: str) -> str:
        """
        Reverse formspec_escape:
          '\\]' -> ']', '\\[' -> '[', '\\;' -> ';', '\\,' -> ',', '\\$' -> '$', '\\\\' -> '\\'
        Order matters: unescape specific tokens first, then backslashes.
        """
        s = s.replace(r'\]', ']').replace(r'\[', '[').replace(r'\;', ';').replace(r'\,', ',').replace(r'\$', '$')
        s = s.replace(r'\\', '\\')
        return s

    def send_command(self, command: str) -> bool:
        """
        Sends a chat command prefixed with /miney to the server.

        :param command: The command string to send after '/miney'.
        :return: True if the message was sent, False otherwise.
        """
        return self.luanti.send_chat_message(f"/miney {command}")

    def run(self, lua_code: str, timeout: int = 10, execution_id: str = None) -> Any:
        """
        Execute Lua code on the server and return the result.

        :param lua_code: The Lua code to execute.
        :param timeout: Maximum wait time in seconds for the result.
        :param execution_id: A unique ID for this execution. If None, one will be generated.
        :return: The result of the Lua execution. Can be None if the script returns no value.
        :raises LuaResultTimeout: When the timeout is reached.
        :raises LuantiConnectionError: When there is no connection to the server or the required 'miney' mod is missing.
        :raises LuantiPermissionError: When the user lacks the required 'miney' privilege on the server.
        :raises LuaError: When the Lua code execution results in an error on the server.
        """
        if not lua_code or lua_code.isspace() or lua_code.strip() == "":
            logger.warning("No Lua code provided to execute.")
            return None

        # Dedent to allow for nicely formatted multiline strings
        lua_code = textwrap.dedent(lua_code)

        if not self.luanti.state.connected or self.luanti.state.state < ClientState.JOINED:
            logger.warning(f"Cannot execute Lua code: not fully connected (state: {self.luanti.state.state})")
            raise LuantiConnectionError("Not fully connected to the server")

        # Ensure the code form is ready before proceeding.
        if not self.form_ready:
            logger.debug("Code form is not ready, requesting it now...")
            self.send_command("form")

            # Wait for the form to become ready
            form_timeout = time.time() + 5
            while not self.form_ready and time.time() < form_timeout:
                time.sleep(0.1)

            if not self.form_ready:
                logger.error("Failed to receive code form from the server after request.")
                raise LuantiConnectionError("Cannot execute Lua code: 'miney:code_form' is not available. "
                                      "Ensure the 'miney' mod is installed on the server.")

        # Generate a unique ID if none was provided
        if execution_id is None:
            execution_id = str(uuid.uuid4())

        # Register the execution ID as pending
        self.pending_lua_results[execution_id] = None

        # Send Lua code through the form with execution ID
        logger.debug(f"Sending Lua code with ID {execution_id}: {lua_code}")
        fields = {
            "lua": lua_code,
            "execute": "true",
            "execution_id": execution_id
        }

        try:
            self.luanti.send_formspec_response("miney:code_form", fields)
        except ValueError as e:
            logger.error(f"Failed to send Lua code: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error sending Lua code: {e}")
            return f"Error: {str(e)}"

        # Wait for the result with polling
        start_time = time.time()
        last_log_time = start_time

        result = None
        while time.time() - start_time < timeout:
            result = self.pending_lua_results.get(execution_id)
            if result is not None:
                break

            # Output status message every 2 seconds
            current_time = time.time()
            if current_time - last_log_time >= 2:
                elapsed = current_time - start_time
                logger.debug(f"Waiting for Lua result (ID: {execution_id}), elapsed: {elapsed:.1f}s/{timeout}s")
                last_log_time = current_time

            time.sleep(0.001)

        # Clean up the pending result entry and get the final result
        parsed_response = self.pending_lua_results.pop(execution_id, None)

        if parsed_response is None:
            logger.error(f"Timeout waiting for Lua execution result (ID: {execution_id})")
            raise LuaResultTimeout(f"Timeout waiting for Lua execution result (ID: {execution_id})")

        logger.debug(f"Received Lua execution response for ID {execution_id}: {parsed_response}")

        # The response is already a parsed dictionary from _handle_miney_code_form
        if "error" in parsed_response:
            # Check if it's a permission error (indicated by the 'admins' key)
            if "admins" in parsed_response:
                admins = parsed_response.get("admins", [])
                command_to_grant = f"/grant {self.luanti.playername} miney"

                if admins:
                    helpful_players = ", ".join(admins)
                    who_can_help = f"The following players can grant this privilege: {helpful_players}"
                else:
                    who_can_help = "No players with the required 'privs' privilege were found on the server."

                error_message = (
                    f"{parsed_response['error']}\n"
                    f"{who_can_help}\n"
                    f"Command to grant privilege: {command_to_grant}"
                )
                raise LuantiPermissionError(error_message)

            # It's a regular Lua execution error
            raise LuaError(parsed_response["error"])

        if "result" in parsed_response:
            final_result = parsed_response["result"]
            logger.debug(f"Successfully processed Lua result for ID {execution_id}")
            return final_result

        # If there's no error and no result, the execution completed without returning a value.
        # This is a valid outcome, so we return None.
        logger.debug(f"Lua execution for ID {execution_id} completed without a return value.")
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
            # json.dumps is a safe way to create a quoted and escaped string
            # that is compatible with Lua's string literal format.
            return json.dumps(data, ensure_ascii=False)
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
        
