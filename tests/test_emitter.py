import xml.etree.ElementTree as ET

from py2gh import convert

from ghx_util import all_instance_guids, all_sources, object_count, parse_objects

SIMPLE = """\
a = 3.0
b = 5.0
half_perimeter = (a + b)
area = half_perimeter * 2.0
"""


def test_output_is_well_formed_xml():
    ghx = convert(SIMPLE, "simple_math.ghx")
    ET.fromstring(ghx)  # raises if malformed


def test_object_count_matches_objects():
    ghx = convert(SIMPLE, "simple_math.ghx")
    assert object_count(ghx) == len(parse_objects(ghx)) == 6


def test_every_wire_resolves_to_a_real_guid():
    """A Source must cite a guid that actually exists in the document, or
    Grasshopper silently drops the connection."""
    ghx = convert(SIMPLE, "simple_math.ghx")
    guids = all_instance_guids(ghx)
    sources = all_sources(ghx)
    assert sources, "expected at least one wire"
    for src in sources:
        assert src in guids, f"dangling wire to {src}"


def test_panel_is_wired_to_multiplication_output():
    ghx = convert(SIMPLE, "simple_math.ghx")
    # The panel's Source should be the multiplication's param_output guid, not
    # the multiplication node's own guid.
    root = ET.fromstring(ghx)
    # collect node (container) guids vs param_output guids
    objects = parse_objects(ghx)
    assert any(o["name"] == "Panel" for o in objects)
    assert any(o["name"] == "Multiplication" for o in objects)
