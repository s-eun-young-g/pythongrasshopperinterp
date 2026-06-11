"""Coverage for the M2 expansion: comparisons, booleans, geometry, lists."""

import xml.etree.ElementTree as ET

import pytest

from py2gh import analyze, convert
from py2gh.ir import NodeKind

from ghx_util import all_instance_guids, all_sources, parse_objects


def names(graph):
    return [n.component_name for n in graph.nodes]


# -- comparisons ------------------------------------------------------------

@pytest.mark.parametrize("op, comp_name", [
    ("<", "Smaller Than"), ("<=", "Smaller Than"),
    (">", "Larger Than"), (">=", "Larger Than"),
    ("==", "Equality"), ("!=", "Equality"),
])
def test_comparison_components(op, comp_name):
    g = analyze(f"a = 1.0\nb = 2.0\nc = (a {op} b)\n")
    assert comp_name in names(g)


def test_or_equal_selects_second_output():
    # `>=` and `>` share the Larger Than component but cite different outputs.
    g_strict = analyze("a = 1.0\nb = 2.0\nc = (a > b)\n")
    g_orequal = analyze("a = 1.0\nb = 2.0\nc = (a >= b)\n")
    strict_port = _terminal_source_port(g_strict)
    orequal_port = _terminal_source_port(g_orequal)
    larger_strict = next(n for n in g_strict.nodes if n.component_name == "Larger Than")
    larger_orequal = next(n for n in g_orequal.nodes if n.component_name == "Larger Than")
    assert strict_port is larger_strict.outputs[0]
    assert orequal_port is larger_orequal.outputs[1]


def _terminal_source_port(graph):
    panel = next(n for n in graph.nodes if n.kind is NodeKind.PANEL)
    return panel.inputs[0].source


# -- booleans ---------------------------------------------------------------

def test_boolean_and_or_not():
    g = analyze("a = 1.0\nb = 2.0\nc = 3.0\nr = (a < b) and (b < c)\n")
    assert "Gate And" in names(g)


def test_boolop_chain_folds_pairwise():
    g = analyze("a = 1.0\nb = 2.0\nc = 3.0\nd = 4.0\n"
                "r = (a < b) and (b < c) and (c < d)\n")
    # three comparisons + two And gates
    assert names(g).count("Gate And") == 2


def test_not_lowers_to_gate_not():
    g = analyze("a = 1.0\nb = 2.0\nr = not (a < b)\n")
    assert "Gate Not" in names(g)


# -- geometry ---------------------------------------------------------------

def test_tuple_builds_construct_point():
    g = analyze("p = (1.0, 2.0, 3.0)\n")
    assert "Construct Point" in names(g)
    point = next(n for n in g.nodes if n.component_name == "Construct Point")
    assert len(point.inputs) == 3
    assert all(ip.source is not None for ip in point.inputs)


def test_two_tuple_pads_z_with_zero():
    g = analyze("p = (1.0, 2.0)\n")
    point = next(n for n in g.nodes if n.component_name == "Construct Point")
    z_source = point.inputs[2].source
    assert z_source.node.kind is NodeKind.SLIDER
    assert z_source.node.data["value"] == 0.0


def test_vector_call():
    g = analyze("v = vector(1.0, 0.0, 0.0)\n")
    assert "Vector XYZ" in names(g)


# -- lists ------------------------------------------------------------------

def test_list_builds_merge_with_n_inputs():
    g = analyze("xs = [1.0, 2.0, 3.0, 4.0]\n")
    merge = next(n for n in g.nodes if n.component_name == "Merge")
    assert len(merge.inputs) == 4
    assert all(ip.source is not None for ip in merge.inputs)


# -- end-to-end emission stays valid ---------------------------------------

def test_expanded_program_emits_resolvable_ghx():
    src = (
        "a = 1.0\n"
        "b = 2.0\n"
        "flag = (a < b) and (b > a)\n"
        "p = (a, b, 3.0)\n"
        "xs = [a, b, 3.0]\n"
    )
    ghx = convert(src, "expanded.ghx")
    ET.fromstring(ghx)  # well-formed
    guids = all_instance_guids(ghx)
    for source in all_sources(ghx):
        assert source in guids, f"dangling wire to {source}"
    objs = {o["name"] for o in parse_objects(ghx)}
    assert {"Smaller Than", "Larger Than", "Gate And", "Construct Point", "Merge"} <= objs
