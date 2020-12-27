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
    pos1 = miney.Node(21, 27, 21, mt.nodes.type.default.dirt)

    mt.nodes.set(pos1)

    pos1_node = mt.nodes.get(pos1)
    assert "name" in pos1_node.__dict__
    assert pos1_node.name in mt.nodes.type
    assert "param1" in pos1_node.__dict__
    assert "param2" in pos1_node.__dict__

    # we create a cube of dirt
    nodes = []
    for x in range(0, 9):
        for y in range(0, 9):
            for z in range(0, 9):
                nodes.append(miney.Node(pos1.x + x, pos1.y + y, pos1.z + z, "default:dirt"))

    # save for later restore
    before = mt.nodes.get(nodes)

    mt.nodes.set(nodes)
    dirt_nodes = mt.nodes.get((nodes[0], nodes[-1]))
    print("dirt_nodes", dirt_nodes)
    assert dirt_nodes[0].name == "default:dirt"
    assert dirt_nodes[-1].name == "default:dirt"
    assert "param1" in dict(dirt_nodes[0])
    assert "param2" in dict(dirt_nodes[0])

    mt.nodes.set(before)
    before_nodes = mt.nodes.get([before[0], before[-1]])
    assert before_nodes[0].name == before[0].name
    assert before_nodes[-1].name == before[-1].name
