Minetest
========

This is the starting point for this library. With creating a Minetest object you also connect to minetest.

In this object are all functions that targets minetest itself.
There is also some properties inside, to get other objects like players or nodes.

:Example:

    >>> from miney import Minetest
    >>>
    >>> mt = Minetest()
    >>>
    >>> # We set the time to midday.
    >>> mt.time_of_day = 0.5
    >>>
    >>> # Write to the servers log
    >>> mt.log("Time is set to midday ...")


.. autoclass:: miney.Minetest
   :members: