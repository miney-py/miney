"""
The MIT License (MIT)

Pycraft Mod Copyright (c) Giuseppe Menegoz (@gmenegoz) & Alessandro Norfo (@alenorfo)
RaspberryJamMod Copyright (c) 2015 Alexander R. Pruss
Lua Copyright (c) 1994�2015 Lua.org, PUC-Rio.
luasocket Copyright (c) Diego Nehab (with socket.lua changed by ARP to load x64/x86 as needed, and minetest compatibility)
tools.lua adapted from lua-websockets Copyright (c) 2012 Gerhard Lipp (with base64 inactivated and minetest compatibility)
base64.lua Copyright (c) 2014 Mark Rogaski and (C) 2012 Paul Moore (changed by ARP to MIME encoding and minetest compatibility)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import math
import miney


def draw_donut(mt, mcx, mcy, mcz, R, r, mcblock):

    positions = []

    for x in range(-R - r, R + r):
        for y in range(-R - r, R + r):
            xy_dist = math.sqrt(x ** 2 + y ** 2)
            if xy_dist > 0:
                ringx = x / xy_dist * R  # nearest point on major ring
                ringy = y / xy_dist * R
                ring_dist_sq = (x - ringx) ** 2 + (y - ringy) ** 2

                for z in range(-R - r, R + r):
                    if ring_dist_sq + z ** 2 <= r ** 2:
                        positions.append(
                            {
                                "x": (mcx + x),
                                "y": (mcz + y),
                                "z": (mcy + z)
                            }
                        )
    print("Spawning", len(positions), "node of", mcblock)
    print(positions)
    mt.node.set(node=positions, name=mcblock)


if miney.is_miney_available():
    mt = miney.Minetest()

    playerPos = mt.player[0].position

    draw_donut(mt, playerPos["x"], playerPos["y"] + 1, playerPos["z"], 4, 2, 'default:glass')
    mt.chat.send_to_all(mt.node.type.default.glass + " donut done")
    print(mt.node.type.default.glass + " donut done")

    draw_donut(mt, playerPos["x"], playerPos["y"] + 1, playerPos["z"], 4, 1, 'default:water_source')
    mt.chat.send_to_all(mt.node.type.default.lava_source + " donut done")
    print(mt.node.type.default.lava_source + " donut done")
else:
    raise miney.MinetestRunError("Please start Minetest with the miney game")
