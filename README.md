# py2gh — Python → Grasshopper

Convert Python code into a Grasshopper definition (`.ghx`) you can open in Rhino.

```bash
pip install -e .
py2gh examples/simple_math.py -o out.ghx
```

```python
# examples/simple_math.py
a = 3.0
b = 5.0
half_perimeter = (a + b)
area = half_perimeter * 2.0
```

becomes a canvas of Number Sliders → Addition / Multiplication components → an
output Panel.

## How it works

```
Python source ──▶ AST analyzer ──▶ IR graph ──▶ .ghx emitter ──▶ Grasshopper
                  (analyzer.py)    (ir.py)       (emitter.py)
```

The IR graph in the middle is the whole point: it decouples "what Python means"
from "what a `.ghx` looks like," so either end can change independently and new
source languages or output formats plug in at the seam.

A wire in a `.ghx` is not a top-level element — it lives on the **downstream
input** as a `Source` item referencing the **upstream object's GUID**. The
emitter reproduces that exactly (verified against a real Grasshopper export).

## Status

Working v0, **structure-validated against a real Grasshopper export** (GH 0.9+,
ArchiveVersion 0.2.2). The Number Slider, Panel, and operator (container +
`param_input`/`param_output`) serializations match the real format
item-for-item, and operator→operator wiring is verified to resolve through
`param_output` GUIDs rather than node GUIDs.

Supported Python: numeric literals (→ sliders), names, binary ops
(`+ - * / ** %`), unary minus, and a small set of maths calls (`sin`, `cos`,
`sqrt`, `abs`). Unsupported constructs raise a clear error.

**Confirmed component GUIDs:** Addition, Multiplication, Negative, Number Slider,
Panel. Still need harvesting (`py2gh --check-guids`): Subtraction, Division,
Power, Modulus, Sine, Cosine, SquareRoot, Absolute. The bundled
`examples/simple_math.py` uses only confirmed components, so it should open
cleanly; run `tools/harvest_components.py` in Grasshopper to fill the rest.

> Note: a wrong GUID floats around online for Multiplication
> (`ce46b74e…`); the value read from a real file is `b8963bb1…`. This is exactly
> why GUIDs are harvested, not trusted from memory.

## Roadmap

- **M0 — skeleton (done):** AST→IR→`.ghx`, arithmetic, sliders/panels, tests, CLI.
- **M1 — open-in-Rhino correctness (mostly done):** serialization rebuilt to
  match a real export item-for-item (alphabetical items, `Bounds`+`Pivot`
  attributes, real Slider/Panel/operator chunks); wiring fixed to cite
  `param_output` GUIDs; core GUIDs confirmed from a real file. *Remaining:*
  harvest the last operator/trig GUIDs, and the one thing that needs a machine
  with Rhino — actually opening the output in Rhino 8 to confirm round-trip.
- **M2 — coverage:** comparisons & booleans, more maths/trig, tuples → points
  /vectors, list literals → GH lists, `rhino3dm` geometry calls → geometry comps.
- **M3 — control flow:** map list comprehensions to data-tree operations; detect
  regions that can't be lowered and wrap them in a single GhPython component
  (the "escape hatch") so any Python still round-trips.
- **M4 — fidelity & UX:** auto-layout that doesn't overlap, groups/labels from
  comments, round-trip (`.ghx` → Python) for testing, binary `.gh` output.
- **M5 — packaging:** PyPI release, optional Rhino.Compute hook to execute and
  screenshot the result for CI.

## Tests

```bash
python -m pytest -q
```
