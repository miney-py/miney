<p align="center">
<img src="https://github.com/miney-py/miney/raw/master/docs/miney-logo.png">
</p>

# Miney - The python interface to Luanti

Miney is the Python API to Luanti/Minetest.

Miney connects locally, over network or internet with the Luanti protocol and provides a pythonic interface to the server, players, blocks and more.

* `PyPI <https://pypi.org/project/miney/>`_

* `Luanti ContentDB <https://content.luanti.org/packages/Miney/miney/>`_

## Documentation

https://miney.readthedocs.io/en/latest/

## Status

https://miney.readthedocs.io/en/latest/changelog.html

**With version 0.5 we removed mineysocket and talking now directly to the server over the Luanti protocol.**

Miney is still in beta, so expect breaking changes.

## Requirement

* Python 3.6+ (tested on 3.12)
* Installed "miney" mod in the server.

# Development

Clone the repo:
```
git clone https://github.com/miney-py/miney.git
```

# TODO

A list of things i'm planning to do. There will be no fixed timeline. 

Feel free to contribute!

* [x] Callbacks
* [ ] Mesecons: Add a python script processor that executes python code. 
* Documentation:
    * [ ] Better first steps guide
    * [ ] Python learning lessons that build on each other
    * [ ] Education material for beginners, teachers and students
    * [ ] Multilanguage
* Native client
    * [ ] Get chunks, blocks and positions of surrounding entities like a normal client
        * Could be interesting for machine learning and bots to make them aware of their surroundings
    * [ ] Normal player movement without using lua
    * [ ] Player interactions like punching and interacting with blocks and entities
* [ ] Async
* Python driven mobs? 
