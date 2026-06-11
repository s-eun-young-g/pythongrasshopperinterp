"""Structural parity against the bundled reference export.

`reference_simple_math.ghx` was produced by an earlier py2gh run and hand-checked
against a real Grasshopper file. GUIDs and emission order are allowed to differ
(Grasshopper resolves by guid, not position), so we compare the *multiset* of
object signatures rather than the raw bytes.
"""

import os

from py2gh import convert

from ghx_util import parse_objects

HERE = os.path.dirname(__file__)
REFERENCE = os.path.join(HERE, "reference_simple_math.ghx")

SIMPLE = """\
a = 3.0
b = 5.0
half_perimeter = (a + b)
area = half_perimeter * 2.0
"""


def signature(objects):
    # (name, nickname, value) frozen into a sortable, comparable multiset
    return sorted(
        (o["name"], o["nickname"], o.get("value")) for o in objects
    )


def test_matches_reference_structure():
    with open(REFERENCE, encoding="utf-8") as f:
        reference = parse_objects(f.read())
    generated = parse_objects(convert(SIMPLE, "simple_math.ghx"))
    assert signature(generated) == signature(reference)
