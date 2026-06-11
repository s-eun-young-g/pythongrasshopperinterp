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


# -- fidelity fixes ---------------------------------------------------------

def _minimal_archive(objects_xml: str) -> str:
    return (
        '<Archive name="Root"><chunks count="1">'
        '<chunk name="Definition"><chunks count="1">'
        '<chunk name="DefinitionObjects">'
        '<items count="1"><item name="ObjectCount" type_name="gh_int32" type_code="3">2</item></items>'
        f'<chunks count="2">{objects_xml}</chunks>'
        '</chunk></chunks></chunk></chunks></Archive>'
    )


def _obj(index, type_guid, name, container_inner):
    return (
        f'<chunk name="Object" index="{index}">'
        f'<items count="2">'
        f'<item name="GUID" type_name="gh_guid" type_code="9">{type_guid}</item>'
        f'<item name="Name" type_name="gh_string" type_code="10">{name}</item>'
        f'</items>'
        f'<chunks count="1"><chunk name="Container">{container_inner}</chunk></chunks>'
        f'</chunk>'
    )


def test_bare_parameter_wire_resolves():
    """A parameter component (no param_output) is its own output: a downstream
    input citing its node guid must resolve."""
    curve = _obj(
        0, "aaaa-curve-type", "Curve",
        '<items count="2">'
        '<item name="InstanceGuid" type_name="gh_guid" type_code="9">11111111-1111-1111-1111-111111111111</item>'
        '<item name="NickName" type_name="gh_string" type_code="10">crv</item>'
        '</items>',
    )
    divide = _obj(
        1, "bbbb-op-type", "Divide Curve",
        '<items count="2">'
        '<item name="InstanceGuid" type_name="gh_guid" type_code="9">22222222-2222-2222-2222-222222222222</item>'
        '<item name="NickName" type_name="gh_string" type_code="10"></item>'
        '</items>'
        '<chunks count="1"><chunk name="param_input" index="0">'
        '<items count="2">'
        '<item name="Name" type_name="gh_string" type_code="10">Curve</item>'
        '<item name="Source" index="0" type_name="gh_guid" type_code="9">11111111-1111-1111-1111-111111111111</item>'
        '</items>'
        '</chunk></chunks>',
    )
    g = read(_minimal_archive(curve + divide))
    div = next(n for n in g.nodes if n.component_name == "Divide Curve")
    assert div.inputs[0].source is not None
    assert div.inputs[0].source.node.component_name == "Curve"


def test_multi_output_source_is_disambiguated():
    """Decompiling a wire from the 2nd output of a multi-output component should
    render an indexed reference like `t1[1]`."""
    from py2gh.decompile import to_python
    from py2gh.ir import Graph, InPort, Node, NodeKind, OutPort

    g = Graph()
    src = Node(NodeKind.OP, "Deconstruct", "guid-a", "ia")
    src.outputs = [OutPort(src, "X", "ox"), OutPort(src, "Y", "oy"), OutPort(src, "Z", "oz")]
    g.nodes.append(src)

    sink = Node(NodeKind.OP, "Addition", "guid-b", "ib")
    ip = InPort(sink, "A", "ipa")
    ip.connect(src.outputs[1])      # read Y, the 2nd output
    sink.inputs = [ip]
    sink.outputs = [OutPort(sink, "R", "or")]
    g.nodes.append(sink)

    py = to_python(g)
    assert "[1]" in py


def test_persistent_scalar_is_read_and_rendered():
    """An unwired input with a typed-in number (PersistentData) should surface
    that value as a literal rather than None."""
    op = _obj(
        0, "cccc-op-type", "Some Op",
        '<items count="2">'
        '<item name="InstanceGuid" type_name="gh_guid" type_code="9">33333333-3333-3333-3333-333333333333</item>'
        '<item name="NickName" type_name="gh_string" type_code="10"></item>'
        '</items>'
        '<chunks count="1"><chunk name="param_input" index="0">'
        '<items count="1">'
        '<item name="Name" type_name="gh_string" type_code="10">Factor</item>'
        '</items>'
        '<chunks count="1"><chunk name="PersistentData">'
        '<items count="1"><item name="Count" type_name="gh_int32" type_code="3">1</item></items>'
        '<chunks count="1"><chunk name="Branch" index="0">'
        '<items count="2">'
        '<item name="Count" type_name="gh_int32" type_code="3">1</item>'
        '<item name="Path" type_name="gh_string" type_code="10">{0}</item>'
        '</items>'
        '<chunks count="1"><chunk name="Item" index="0">'
        '<items count="1"><item name="Factor" type_name="gh_double" type_code="6">3.5</item></items>'
        '</chunk></chunks>'   # close Item
        '</chunk></chunks>'   # close Branch
        '</chunk></chunks>'   # close PersistentData
        '</chunk></chunks>',  # close param_input
    )
    from py2gh.decompile import to_python

    g = read(_minimal_archive(op))   # ObjectCount says 2 but only 1 object: reader ignores the count
    node = g.nodes[0]
    assert node.inputs[0].persistent is not None
    assert node.inputs[0].persistent.value == 3.5
    assert "3.5" in to_python(g)
