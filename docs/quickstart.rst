Quickstart
==========

Welcome in the block sandbox!

Blockgames like Minecraft or Minetest give you the ideal playground for creative playing and building just like a real sandbox.
But other than real sandboxes, you can work on very large worlds together with your friends over the internet.
And you can use (very simplified) physics, save the progress and many more.

But what about learning programming while expressing your creativity? Why not automate things? Or build even greater things?

Installation
------------

Windows
^^^^^^^

 * Download the latest precompiled Miney distribution: https://github.com/miney-py/miney_distribution/releases
 * Start the miney-launcher.exe and click on "Quickstart". This will open Minetest directly into a game and IDLE, the IDE shipped with python.

Linux
^^^^^

Tested under lubuntu 20.04LTS

$ sudo apt-get install minetest fonts-crosextra-caladea fonts-crosextra-carlito minetest-mod-moreblocks minetest-mod-moreores minetest-mod-pipeworks minetest-server minetestmapper

$ sudo apt-get install luajit lua-socket lua-cjson idle3 python3-pip

$ pip3 install miney

Then install the mineysocket mod in minetest

$ cd ~/.minetest/mods

$ git clone https://github.com/miney-py/mineysocket.git

Don't forget to enable the mods in the configuration tab for your new game!

MacOS
^^^^^

Untested

First lines of code
-------------------

The first lines of code with miney should be the import statement and the creation of the miney object "mt". This will
connect miney to your already running Minetest.

::

    import miney

    mt = miney.Minetest()

.. Important::

    Whenever you see a object "mt" in the documentation, it was created with this line!
