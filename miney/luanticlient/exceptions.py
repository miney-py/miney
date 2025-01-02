"""
Custom exceptions for the Luanti client.
"""

class LuantiTimeoutError(Exception):
    """Exception raised when a timeout occurs during communication with the server."""
    pass


class LuantiConnectionError(Exception):
    """Exception raised when there is a connection error with the server."""
    def __init__(self, message: str, reason_code: int | None = None):
        super().__init__(message)
        self.reason_code = reason_code


class LuantiPermissionError(Exception):
    """Exception raised when an action is denied due to insufficient privileges."""
    pass
