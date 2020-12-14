"""
Test all node related.
"""

import miney


def test_node_types(mt: miney.Minetest):
    assert len(mt.nodes.type) > 400
    assert mt.nodes.type.default.dirt == "default:dirt"
    assert mt.nodes.type["default"]["dirt"] == "default:dirt"
    assert len(mt.nodes.type["default"]) > 400


def test_node_set_and_get(mt: miney.Minetest):
    pos1 = {"x": 22, "y": 28, "z": 22}

    mt.nodes.set(pos1, name=mt.nodes.type.default.dirt, offset={"x": -1, "y": -1, "z": -1})

    pos1_node = mt.nodes.get(pos1)
    assert "name" in pos1_node
    assert pos1_node["name"] in mt.nodes.type
    assert "param1" in pos1_node
    assert "param2" in pos1_node

    # we create a cube of dirt
    nodes = []
    for x in range(0, 9):
        for y in range(0, 9):
            for z in range(0, 9):
                nodes.append({"x": pos1["x"] + x, "y": pos1["y"] + y, "z": pos1["z"] + z, "name": "default:dirt"})

    # save for later restore
    before = mt.nodes.get(nodes[0], nodes[-1], relative=False)

    mt.nodes.set(nodes, name="default:dirt")
    dirt_nodes = mt.nodes.get(nodes[0], nodes[-1])
    assert dirt_nodes[0]["name"] in mt.nodes.type
    assert dirt_nodes[0]["name"] == "default:dirt"
    assert dirt_nodes[-1]["name"] in mt.nodes.type
    assert dirt_nodes[-1]["name"] == "default:dirt"
    assert "param1" in dirt_nodes[0]
    assert "param2" in dirt_nodes[0]

    mt.nodes.set(before, name="default:dirt")
    before_nodes = mt.nodes.get(before[0], before[-1])
    assert before_nodes[0]["name"] == before[0]["name"]
    assert before_nodes[-1]["name"] == before[-1]["name"]
