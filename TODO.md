# TODO

A list of things i'm planning to do. There will be no fixed timeline.

Feel free to contribute!

## General

* [ ] miney command line:
  * [ ] show miney version
  * [x] integrate check_setup.py
  * [ ] Luanti upgrade
  * [x] Use https://github.com/pkgforge-dev/Anylinux-AppImages for linux
* [ ] automate pypi and contentdb release

## API

* [ ] Convenience aliases for `Player.move()`: `teleport()`, `look_at()`, `fly_to()`, `turn()`
  * Thin wrappers around `move()`, not separate implementations
  * Each one documents the equivalent `move()` call, so the alias teaches the general function
* [ ] Callbacks
  * [x] Basic API and some callbacks implemented
  * [ ] Implement more "register_on_..." functions
* [ ] Asyncio
* [ ] Miney Proxy
  * funnel all functions/commands through a single client connection
* [ ] Mesecons: Add a python script processor that executes python code.
* Python driven mobs?

## Native client

* [ ] Get chunks, blocks and positions of surrounding entities like a normal client
  * Could be interesting for machine learning and bots to make them aware of their surroundings
* [ ] Normal player movement without using lua
* [ ] Player interactions like punching and interacting with blocks and entities

## Documentation

* [ ] Better first steps guide
* [ ] Python learning lessons that build on each other
* [ ] Education material for beginners, teachers and students
* [ ] Multilanguage

## Infrastructure

* [ ] Github-Actions
  * [x] run tests
  * [x] Tests for pull requests
  * [ ] Build and push to pypi for tagged commits
  * [ ] Build and push to Luanti ContentDB for tagged commits
