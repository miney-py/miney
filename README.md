<p align="center">
<img src="https://github.com/miney-py/miney/raw/master/docs/miney-logo.png">
</p>

# Miney - The python interface to Luanti

Miney is the Python API to Luanti/Minetest.

Miney connects locally, over network or internet with the Lunanti protocol and provides a pythonic interface to the server, players, blocks and more.

## Documentation

https://miney.readthedocs.io/en/latest/

## Status

**With version 0.5 we removed mineysocket and talking now directly to the server over the Lunanti protocol!**

This is a major change and will break existing code! But it's also very cool, because you now only need the miney mod 
in the server and the "miney" python module. No special compiled server version and no mineysocket mod anymore! 
That makes it straightforward to install. Fast and easy, just like Python!

## Requirement

* Python 3.6+ (tested on 3.12)
* Installed "miney" mod in the server.

# Development

Clone the repo:
```
git clone https://github.com/miney-py/miney.git
```