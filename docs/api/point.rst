Point
=====

Represents a point in a three-dimensional space.

A ``Point`` behaves like the builtins you already know: you can add and subtract points, multiply and divide
them by a number, take their ``len()``, iterate over them and index them like a tuple.

.. autoclass:: miney.Point
   :members:

.. rubric:: Vector

A direction rather than a place. :attr:`~miney.Player.look_dir` returns one, and you never have to create a
``Vector`` yourself.

.. autoclass:: miney.vector.Vector
   :members:
