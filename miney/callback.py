import string
from random import choices
import miney
import logging

logger = logging.getLogger(__name__)

class Callback:
    """Register callbacks inside Luanti, to receive events from Lua"""
    def __init__(self, luanti: miney.Luanti):
        self.lt = luanti

    def activate(self, event: str, callback: callable, parameters: dict = None):
        """
        Register a callback for an event.

        :param event: Event to register for
        :param callback: The function to be called on events
        :param parameters: Some events need parameters
        :return: None
        """
        # TODO: Implement Callbacks
        logger.warning("Callbacks are not yet implemented.")
