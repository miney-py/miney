Exceptions
==========

Everything Miney raises at you carries a name that says what went wrong, so you can catch exactly the case you
want to handle:

.. code-block:: python

   try:
       lt = miney.Luanti()
   except miney.LuantiConnectionError:
       print("No server there. Start one with: uv run miney start")

All of these are importable straight from ``miney``, for example ``miney.LuaError``.

.. automodule:: miney.exceptions
   :members: