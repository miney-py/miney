"""
Test all node related.
"""

import miney


def test_node_types(mt: miney.Minetest):
    assert len(mt.node.type) > 400
    assert mt.node.type.default.dirt == "default:dirt"
    assert mt.node.type["default"]["dirt"] == "default:dirt"
    assert len(mt.node.type["default"]) > 400


def test_node_set_and_get(mt: miney.Minetest):
    pos = mt.player[0].position
    pos1 = {"x": pos["x"] + 10, "y": pos["y"] + 10, "z": pos["z"] + 10}
    pos2 = {"x": pos["x"] + 20, "y": pos["y"] + 20, "z": pos["z"] + 20}

    # assure we're hovering in the air
    mt.player[0].fly = True
    assert mt.player[0].fly

    print(mt.node.get(pos1))
    pos1_node = mt.node.get(pos1)
    assert "name" in pos1_node
    assert pos1_node["name"] in mt.node.type
    assert "param1" in pos1_node
    assert "param2" in pos1_node

    nodes = []
    for x in range(0, 9):
        for y in range(0, 9):
            for z in range(0, 9):
                nodes.append({"x": pos1["x"] + x, "y": pos1["y"] + y, "z": pos1["z"] + z, "name": "default:dirt"})

    # save for later recovery
    before = mt.node.get(nodes[0], nodes[-1])

    mt.node.set(nodes, name="default:dirt")
    dirt_nodes = mt.node.get(nodes[0], nodes[-1])
    assert dirt_nodes[0]["name"] in mt.node.type
    assert dirt_nodes[0]["name"] == "default:dirt"
    assert dirt_nodes[-1]["name"] in mt.node.type
    assert dirt_nodes[-1]["name"] == "default:dirt"
    assert "param1" in dirt_nodes[0]
    assert "param2" in dirt_nodes[0]

    mt.node.set(before, name="default:dirt")
    before_nodes = mt.node.get(before[0], before[-1])
    assert before_nodes[0]["name"] == before[0]["name"]
    assert before_nodes[-1]["name"] == before[-1]["name"]
