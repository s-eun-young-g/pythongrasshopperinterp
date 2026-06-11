"""Native geometry calls (line/divide_curve/...) and Boolean Toggle, both ways."""

import xml.etree.ElementTree as ET

import pytest

from py2gh import analyze, convert, decompile_ghx, read
from py2gh.ir import NodeKind

from ghx_util import all_instance_guids, all_sources, parse_objects


def names(graph):
    return [n.component_name for n in graph.nodes]


# -- geometry forward -------------------------------------------------------

def test_line_call_builds_line_component():
    g = analyze("a = (0.0, 0.0, 0.0)\nb = (1.0, 0.0, 0.0)\nc = line(a, b)\n")
    assert "Line" in names(g)
    line = next(n for n in g.nodes if n.component_name == "Line")
    assert [ip.source.node.component_name for ip in line.inputs] == \
        ["Construct Point", "Construct Point"]


def test_geometry_chain_emits_valid_resolvable_ghx():
    src = (
        "span = 10.0\n"
        "n = 5.0\n"
        "a = (0.0, 0.0, 0.0)\n"
        "b = (span, 0.0, 0.0)\n"
        "chord = line(a, b)\n"
        "bay = divide_curve(chord, n)\n"
        "truss = polyline(bay, False)\n"
    )
    ghx = convert(src, "mini_truss.ghx")
    ET.fromstring(ghx)
    guids = all_instance_guids(ghx)
    for s in all_sources(ghx):
        assert s in guids
    emitted = {o["name"] for o in parse_objects(ghx)}
    assert {"Line", "Divide Curve", "PolyLine", "Boolean Toggle"} <= emitted


def test_too_many_args_is_rejected():
    from py2gh.analyzer import UnsupportedPython
    with pytest.raises(UnsupportedPython):
        analyze("x = unit_z(1.0, 2.0)\n")   # Unit Z takes one argument


# -- geometry reverse -------------------------------------------------------

def test_decompile_renders_native_geometry_calls():
    import os
    truss = os.path.join(os.path.dirname(__file__), "..", "examples", "truss2d.ghx")
    py = decompile_ghx(open(truss, encoding="utf-8").read())
    for call in ("line(", "divide_curve(", "polyline(", "join_curves(",
                 "pipe(", "solid_union("):
        assert call in py


# -- boolean toggle ---------------------------------------------------------

def test_boolean_literal_becomes_toggle_and_emits():
    g = analyze("flag = True\nother = False\n")
    toggles = [n for n in g.nodes if n.kind is NodeKind.TOGGLE]
    assert {t.data["value"] for t in toggles} == {True, False}
    ghx = convert("flag = True\n", "t.ghx")
    assert "Boolean Toggle" in {o["name"] for o in parse_objects(ghx)}


def test_toggle_round_trips_through_ghx():
    ghx = convert("flag = True\n", "t.ghx")
    g = read(ghx)
    tog = next(n for n in g.nodes if n.kind is NodeKind.TOGGLE)
    assert tog.data["value"] is True
    assert "True" in decompile_ghx(ghx)
