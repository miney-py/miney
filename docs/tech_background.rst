.. image:: python-logo.png
   :alt: Python logo
   :align: right

Technical Background
=====================

This page provides an inside view of how Miney works.

Miney's basic idea is, to use `Luanti <https://www.luanti.org/>`_ (formerly Minetest) with `Python <https://www.python.org/>`_.

Luanti's main programming language (besides C++) is `Lua <https://www.lua.org/>`_ and it provides a mighty Lua-API for mod programming.
But Lua isn't the ideal programming language to start programming and mod programming isn't fun,
if you just want to play around with a sandbox.
So we need something like an interface that is accessible by Python.

The interface
------------------------------

Miney implements a native Luanti client in Python. This client connects to the Luanti server just like a regular player would.
This approach allows Miney to interact with the game world directly.

To bridge the gap between Python and Lua, Miney relies on a companion mod, the `miney` mod, which must be installed on the Luanti server.
This mod provides the necessary server-side functions to receive Lua code from the Miney client, execute it, and send back the results.
The most important function is the one that executes arbitrary Lua code.

Miney uses this capability to execute Lua code inside Luanti, effectively giving you control over the game via Python.

.. note::

   **And you can use Miney without knowing any Lua or even seeing a single line of Lua code.**

.. dropdown:: Data Transfer via Formspecs

   The communication between the Python client and the Lua mod is built upon Luanti's formspec system. Formspecs are typically used to create graphical user interface (GUI) forms for players, such as inventory screens or dialog boxes. Miney repurposes this system for programmatic data exchange.

   Here's how it works:

   #. **Sending Code to the Server**: When you execute a command in Python that requires interaction with the game world, the Miney client constructs a Lua code snippet. It then sends this code to the server by programmatically "submitting" a form with the form name ``miney:code_form``. The Lua code is embedded within one of the form's fields.

   #. **Execution on the Server**: The ``miney`` mod on the server has a listener registered for this specific form. When it receives the submission, it extracts the Lua code from the form fields and executes it within a sandboxed environment.

   #. **Returning Results to the Client**: After execution, the Lua script gathers the results (e.g., a node's properties, a list of players). The ``miney`` mod then sends a *new* formspec back to the client. This new formspec contains the execution results, typically serialized as a JSON string, in a result field.

   #. **Receiving Results in Python**: The Miney client, which is listening for incoming formspecs, receives this new form. It parses the fields, extracts the JSON result string, deserializes it back into a Python object, and returns it to the calling function.

   This clever use of the formspec system allows for a robust, bidirectional communication channel without requiring any changes to the core Luanti engine. It effectively turns a GUI mechanism into a remote procedure call (RPC) system.


What you need to get started
----------------------------------------------------

Getting started with Miney is straightforward. You only need two components:

1. The **Miney Python package**: Install it using pip: ``pip install miney``
2. The **Miney mod**: This mod must be installed in your Luanti server's content database.

With this setup, you no longer need to worry about external dependencies or compiling anything yourself, regardless of your operating system.
This simplifies the process significantly compared to the old architecture.
