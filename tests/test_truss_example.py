"""Smoke + resolution tests against the bundled real-world truss definition."""

import ast
import os

from py2gh import decompile_ghx, describe_ghx, read

HERE = os.path.dirname(__file__)
TRUSS = os.path.join(HERE, "..", "examples", "truss2d.ghx")


def _ghx():
    with open(TRUSS, encoding="utf-8") as f:
        return f.read()


def test_reads_full_definition():
    g = read(_ghx())
    assert len(g.nodes) == 45


def test_describe_covers_the_pipeline():
    report = describe_ghx(_ghx())
    for name in ("Surface", "Divide Curve", "Construct Point", "Join Curves",
                 "Pipe", "Solid Union"):
        assert name in report


def test_decompile_is_valid_python():
    ast.parse(decompile_ghx(_ghx()))


def test_most_wired_inputs_resolve():
    """The bare-parameter fix should resolve the large majority of wires that
    actually carry a Source (unwired persistent-data inputs are excluded)."""
    g = read(_ghx())
    wired = [ip for n in g.nodes for ip in n.inputs if ip.sources]
    resolved = [ip for ip in wired if ip.source is not None]
    # every input we recorded a Source for should now point at a real node
    assert wired and len(resolved) == len(wired)


def test_multi_output_components_are_dereferenced():
    # Deconstruct/End Points feed coordinate constructors via specific outputs.
    assert "[1]" in decompile_ghx(_ghx())
