.. image:: images/miney-slogan.png
   :alt: Miney logo
   :align: center
   :class: miney-logo-mainpage


Welcome to the Miney documentation!
====================================

Blockgames like Minecraft or `Minetest <https://www.minetest.net/>`_ give you the ideal playground for creative playing and building just like a real sandbox.
But other than real sandboxes, you can work on very large worlds together with your friends over the internet.
And you can use (very simplified) physics, save the progress and more.

But what about learning programming while expressing your creativity? Why not automate things? Or build even greater things?

What is Miney?
----------------

Miney provides you with an `Python <https://www.python.org/>`_ programming interface to `Minetest <https://www.minetest.net/>`_.

First goal is to have fun with a 3D sandbox for Python.
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

**Do whatever you like:**

* Play and fiddle around while learning python
* Visualize data in unusual ways
* Automate things with bots
* Connect minetest to external services like twitter, ebay or whatsoever
* Do whatever you want!

.. important::

   For the best way to get everything running, take a look at the :doc:`quickstart` page.

.. warning::

   Miney is currently in beta, so it's usable but the API may change at any point.

Why Python?
-------------

.. image:: images/python-logo.png
   :alt: Python logo
   :align: right
Python is a great programming language for beginners and experts.

Some marketing text from the `Python website <https://www.python.org/about/>`_:

   | Python is powerful... and fast;
   | plays well with others;
   | runs everywhere;
   | is friendly & easy to learn;
   | is Open.

   These are some of the reasons people who use Python would rather not use anything else.

And it's popular! And cause of that it has a `giant package index <https://pypi.org/>`_ filled by over 450.000 users!


Why Minetest?
---------------
.. image:: images/minetest-logo.png
   :alt: Python logo
   :align: left

Why not Minecraft? Minetest is free. Not only you don't have to pay for Minetest (consider to `donate <https://www.minetest.net/get-involved/#donate>`_!), it's also open source!
That's a big point, if you try to use this for example in a classroom.

Also modding for minecraft isn't that easy, cause there is no official API or an embedded scripting language like Lua
in Minetest. Mods have to be written in Java, but have to be recompiled on every Minecraft update.
Cause of that many attempt for APIs appeared and disappeared in recent years.

In contrast Minetest modding in Lua is easy: no compilation, a official API and all game logic is also in Lua.

Table of Contents
-----------------

.. toctree::
   :maxdepth: 1
   :caption: Getting started

   getting_started/quickstart
   getting_started/basics

.. toctree::
   :maxdepth: 1
   :caption: Reference

   objects/index
   helpers
   tech_background

Miney version: |release|