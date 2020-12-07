import string
from random import choices
import miney


class Callback:
    """Register callbacks inside minetest, to receive events from Lua"""
    def __init__(self, mt: miney.Minetest):
        self.mt = mt

    def activate(self, event: str, callback: callable, parameters: dict = None):
        """
        Register a callback for an event.

        :param event: Event to register for
        :param callback: The function to be called on events
        :param parameters: Some events need parameters
        :return: None
        """
        # Match answer to request
        result_id = ''.join(choices(string.ascii_lowercase + string.ascii_uppercase + string.digits, k=6))

        self.mt.send(
            {
                'activate_event':
                    {
                        'event': event,
                    },
                'id': result_id
            }
        )
