import ast

import pytest

from py2gh import analyze
from py2gh.analyzer import UnsupportedPython
from py2gh.ir import NodeKind

SIMPLE = """\
a = 3.0
b = 5.0
half_perimeter = (a + b)
area = half_perimeter * 2.0
"""


def kinds(graph):
    return [n.kind for n in graph.nodes]


def test_simple_math_node_inventory():
    g = analyze(SIMPLE)
    counts = {k: kinds(g).count(k) for k in NodeKind}
    assert counts[NodeKind.SLIDER] == 3   # a, b, and the literal 2.0
    assert counts[NodeKind.OP] == 2       # Addition, Multiplication
    assert counts[NodeKind.PANEL] == 1    # area is a terminal result


def test_named_vs_inline_slider_nicknames():
    g = analyze(SIMPLE)
    nicks = {n.data.get("value"): n.nickname
             for n in g.nodes if n.kind is NodeKind.SLIDER}
    assert nicks[3.0] == "a"
    assert nicks[5.0] == "b"
    assert nicks[2.0] == "const3"   # inline literal, 3rd slider created


def test_only_terminal_values_get_panels():
    g = analyze(SIMPLE)
    panels = [n for n in g.nodes if n.kind is NodeKind.PANEL]
    assert [p.nickname for p in panels] == ["area"]


def test_wiring_addition_inputs():
    g = analyze(SIMPLE)
    add = next(n for n in g.nodes if n.component_name == "Addition")
    # both inputs are wired to slider outputs
    assert all(ip.source is not None for ip in add.inputs)
    assert {ip.source.node.nickname for ip in add.inputs} == {"a", "b"}


def test_unary_minus_literal_folds_to_slider():
    g = analyze("x = -4.0\n")
    sliders = [n for n in g.nodes if n.kind is NodeKind.SLIDER]
    assert len(sliders) == 1
    assert sliders[0].data["value"] == -4.0


def test_math_call_lowers_to_component():
    g = analyze("y = sqrt(2.0)\n")
    assert any(n.component_name == "SquareRoot" for n in g.nodes)


@pytest.mark.parametrize("src", [
    "for i in range(3): pass\n",  # control flow
    "a, b = 1, 2\n",            # tuple unpacking
    "y = foo(1)\n",             # unknown call
    "y = True\n",               # boolean literal (no toggle emitter yet)
    "y = (1 < 2 < 3)\n",        # chained comparison
    "y = (1, 2, 3, 4)\n",       # 4-tuple is not a point/vector
    "y = []\n",                 # empty list
])
def test_unsupported_raises(src):
    with pytest.raises(UnsupportedPython):
        analyze(src)


def test_undefined_name_raises():
    with pytest.raises(UnsupportedPython):
        analyze("y = q + 1\n")
