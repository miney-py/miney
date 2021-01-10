"""
Test all node related.
"""

import miney


def test_node_types(mt: miney.Minetest):
    assert len(mt.nodes.name) > 400
    assert mt.nodes.name.default.dirt == "default:dirt"
    assert mt.nodes.name["default"]["dirt"] == "default:dirt"
    assert len(mt.nodes.name["default"]) > 400


def test_node_set_and_get_single(mt: miney.Minetest):
    pos1 = miney.Node(10, 10, 10, mt.nodes.name.default.dirt)

    before = mt.nodes.get(pos1)

    mt.nodes.set(pos1)

    pos1_node = mt.nodes.get(pos1)
    assert "name" in pos1_node.__dict__
    assert pos1_node.name in mt.nodes.name
    assert "param1" in pos1_node.__dict__
    assert "param2" in pos1_node.__dict__

    mt.nodes.set(before)
    restored = mt.nodes.get(pos1)
    assert restored.name != mt.nodes.name.default.dirt


def test_node_set_and_get_multiple(mt: miney.Minetest):
    pos1 = miney.Node(10, 10, 10, mt.nodes.name.default.dirt)

    # we create a cube of dirt
    set_nodes = []
    for x in range(0, 9):
        for y in range(0, 9):
            for z in range(0, 9):
                set_nodes.append(miney.Node(pos1.x + x, pos1.y + y, pos1.z + z, "default:dirt"))

    # save for later restore
    before = mt.nodes.get((set_nodes[0], set_nodes[-1]))

    mt.nodes.set(set_nodes)
    dirt_nodes = mt.nodes.get((set_nodes[0], set_nodes[-1]))
    assert dirt_nodes[0].name == "default:dirt"
    assert dirt_nodes[-1].name == "default:dirt"
    assert "param1" in dict(dirt_nodes[0])
    assert "param2" in dict(dirt_nodes[0])

    mt.nodes.set(before)
    restored_nodes = mt.nodes.get([before[0], before[-1]])
    assert restored_nodes[0].name == before[0].name != "default:dirt"
    assert restored_nodes[-1].name == before[-1].name != "default:dirt"
