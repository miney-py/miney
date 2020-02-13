"""
Credits for this exmaple goes to Giuseppe Menegoz (@gmenegoz) & Alessandro Norfo (@alenorfo) and others.
For details look in LICENSE_pycraft.
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
    print("Spawning", len(positions), "nodes of", mcblock)
    mt.node.set(positions, mcblock)


if miney.is_miney_available():
    if not miney.is_miney_available():
        raise miney.MinetestRunError("Please start Minetest with the miney game")
    mt = miney.Minetest()

    playerPos = mt.player[0].position

    draw_donut(mt, playerPos["x"], playerPos["y"] + 1, playerPos["z"], 18, 6, mt.node.type.default.glass)
    mt.chat.send_to_all(mt.node.type.default.glass + " donut done")
    print(mt.node.type.default.glass + " donut done")

    draw_donut(mt, playerPos["x"], playerPos["y"] + 1, playerPos["z"], 18, 6, mt.node.type.default.water_source)
    mt.chat.send_to_all(mt.node.type.default.lava_source + " donut done")
    print(mt.node.type.default.lava_source + " donut done")
else:
    raise Exception("Please run miney before running this example. \n"
                    "For that press the Quickstart button in the launcher or type this in IDLE:\n"
                    "import miney\n"
                    "miney.run_miney_game()")
