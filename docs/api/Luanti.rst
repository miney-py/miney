Luanti
======

This is the starting point for this library. With creating a Luanti object you also connect to a Luanti server.

In this object are all functions that targets Luanti itself.
There is also some properties inside, to get other objects like players or nodes.

:Example:

    >>> from miney import Luanti
    >>>
    >>> lt = Luanti()
    >>>
    >>> # We set the time to midday.
    >>> lt.time_of_day = 0.5
    >>>
    >>> # Write to the servers log
    >>> lt.log("Time is set to midday ...")


.. autoclass:: miney.Luanti
   :members:

.. rubric:: Component Classes

The following classes are accessed through properties of the main ``Luanti`` object.

.. toctree::
   :maxdepth: 1

   chat
   inventory
   lua
   nodes
   player
   point
