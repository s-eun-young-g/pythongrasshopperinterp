"""Reverse pipeline: .ghx -> IR -> {describe, decompile}, and round-trips."""

import ast
import os

from py2gh import analyze, convert, decompile_ghx, describe_ghx, read
from py2gh.ir import NodeKind

from ghx_util import parse_objects

HERE = os.path.dirname(__file__)
REFERENCE = os.path.join(HERE, "reference_simple_math.ghx")

SIMPLE = """\
a = 3.0
b = 5.0
half_perimeter = (a + b)
area = half_perimeter * 2.0
"""


def signature(graph):
    return sorted(
        (n.kind.value, n.component_name,
         n.data.get("value") if n.kind is NodeKind.SLIDER else None)
        for n in graph.nodes
    )


# -- reader -----------------------------------------------------------------

def test_reader_rebuilds_reference_inventory():
    with open(REFERENCE, encoding="utf-8") as f:
        g = read(f.read())
    kinds = [n.kind for n in g.nodes]
    assert kinds.count(NodeKind.SLIDER) == 3
    assert kinds.count(NodeKind.OP) == 2
    assert kinds.count(NodeKind.PANEL) == 1


def test_reader_resolves_wiring():
    with open(REFERENCE, encoding="utf-8") as f:
        g = read(f.read())
    add = next(n for n in g.nodes if n.component_name == "Addition")
    # Addition's two inputs resolve back to the a and b sliders.
    assert {ip.source.node.nickname for ip in add.inputs} == {"a", "b"}
    panel = next(n for n in g.nodes if n.kind is NodeKind.PANEL)
    # Panel resolves to the Multiplication output, not a dangling guid.
    assert panel.inputs[0].source is not None
    assert panel.inputs[0].source.node.component_name == "Multiplication"


def test_read_emitted_output_roundtrips_structure():
    """convert(py) -> read(ghx) yields the same node inventory as analyze(py)."""
    forward = analyze(SIMPLE)
    back = read(convert(SIMPLE, "simple_math.ghx"))
    assert signature(back) == signature(forward)


# -- describe ---------------------------------------------------------------

def test_describe_lists_inputs_and_outputs():
    with open(REFERENCE, encoding="utf-8") as f:
        report = describe_ghx(f.read())
    assert "Number Sliders" in report
    assert "a " in report and "b " in report
    assert "Addition" in report and "Multiplication" in report
    assert "area" in report


# -- decompile --------------------------------------------------------------

def test_decompile_produces_valid_python():
    with open(REFERENCE, encoding="utf-8") as f:
        py = decompile_ghx(f.read())
    ast.parse(py)  # must be syntactically valid


def test_decompiled_python_reanalyzes_to_same_structure():
    """The strong round-trip: .ghx -> Python -> .ghx has matching structure."""
    with open(REFERENCE, encoding="utf-8") as f:
        ghx = f.read()
    py = decompile_ghx(ghx)
    regraph = analyze(py)
    original = parse_objects(ghx)
    regenerated = parse_objects(convert(py, "rt.ghx"))

    def names(objs):
        return sorted(o["name"] for o in objs)

    assert names(regenerated) == names(original)


def test_decompile_recovers_arithmetic():
    py = decompile_ghx(open(REFERENCE, encoding="utf-8").read())
    # The multiplication result is the terminal 'area' panel; decompile should
    # surface an `area = ... * ...` (or `area = <var>` referencing it).
    assert "area" in py
    assert "*" in py and "+" in py
