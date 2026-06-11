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

Supported Python:

- numeric literals (→ sliders), names, unary minus
- binary ops `+ - * / ** %`
- maths calls `sin`, `cos`, `sqrt`, `abs`
- **comparisons** `< <= > >= == !=` (each lowers to a Larger/Smaller/Equality
  component; the `…=` forms reuse the component's second boolean output)
- **booleans** `and`, `or`, `not` (→ Gate And/Or/Not; chains fold pairwise)
- **tuples** `(x, y[, z])` → Construct Point, and `vector(x, y, z)` → Vector XYZ
  (a 2-tuple pads Z with a zero slider)
- **list literals** `[a, b, c]` → a Merge component (a Grasshopper list)

Unsupported constructs (control flow, multi-target assignment, boolean literals,
chained comparisons, unknown calls) raise a clear error with a line number.

**Confirmed component GUIDs:** Addition, Multiplication, Negative, Number Slider,
Panel. Still need harvesting (`py2gh --check-guids`): the remaining arithmetic
(Subtraction, Division, Power, Modulus), trig (Sine, Cosine, SquareRoot,
Absolute), and every component added in M2 (Larger/Smaller Than, Equality, Gate
And/Or/Not, Construct Point, Vector XYZ, Merge). The structural machinery
(graph, wiring, XML) is fully tested regardless; only whether Grasshopper can
*resolve* an unconfirmed GUID is at stake. The bundled `examples/simple_math.py`
uses only confirmed components, so it opens cleanly; run
`tools/harvest_components.py` in Grasshopper to fill the rest.

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
- **M2 — coverage (in progress):** comparisons & booleans, tuples → points
  /vectors, and list literals → GH lists are **done** (analyzer + IR + emitter,
  fully tested). *Remaining:* harvest the new components' GUIDs, and add
  `rhino3dm` geometry calls → geometry components.
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
