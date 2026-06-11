"""Component registry: the dictionary that maps an abstract operation to a real
Grasshopper component (its GUID, display name, and port names).

WHY THIS IS DATA, NOT CODE
--------------------------
A Grasshopper component is identified in a .ghx by a GUID. Core components have
stable GUIDs, but *every third-party plugin* introduces its own, so no hardcoded
table can ever be complete. The registry is therefore plain data that you can
extend or correct against your own Rhino install (see tools/harvest_components.py,
which dumps the authoritative name -> GUID table from a running Grasshopper).

VERIFICATION STATUS
-------------------
GUIDs marked CONFIRMED are widely documented core GUIDs. GUIDs marked VERIFY are
best-effort and should be confirmed with the harvest tool before you rely on the
output opening cleanly. The rest of the pipeline (graph building, wiring, XML
structure) does not depend on these values being right -- only whether
Grasshopper can *resolve* the component does.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ComponentSpec:
    key: str               # internal name, e.g. "add"
    name: str              # Grasshopper display name, e.g. "Addition"
    guid: str              # component type GUID
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    confirmed: bool = False


# Operators: Math > Operators. All take two inputs (A, B) -> one result (R).
# CONFIRMED values were read out of a real Grasshopper export; note Multiplication
# is b8963bb1..., NOT the ce46b74e... that floats around online (that was wrong).
_OPERATORS = [
    ComponentSpec("add", "Addition",       "a0d62394-a118-422d-abb3-6af115c75b25", ("A", "B"), ("R",), confirmed=True),
    ComponentSpec("mul", "Multiplication", "b8963bb1-aa57-476e-a20e-ed6cf635a49c", ("A", "B"), ("R",), confirmed=True),
    ComponentSpec("sub", "Subtraction",    "VERIFY-subtraction-guid",   ("A", "B"), ("R",)),
    ComponentSpec("div", "Division",       "VERIFY-division-guid",      ("A", "B"), ("R",)),
    ComponentSpec("pow", "Power",          "VERIFY-power-guid",         ("A", "B"), ("R",)),
    ComponentSpec("mod", "Modulus",        "VERIFY-modulus-guid",       ("A", "B"), ("R",)),
]

# Unary maths/trig: one input -> one output.
_FUNCTIONS = [
    ComponentSpec("neg",  "Negative",  "a3371040-e552-4bc8-b0ff-10a840258e88", ("x",), ("y",), confirmed=True),
    ComponentSpec("sin",  "Sine",      "VERIFY-sine-guid",     ("x",), ("y",)),
    ComponentSpec("cos",  "Cosine",    "VERIFY-cosine-guid",   ("x",), ("y",)),
    ComponentSpec("sqrt", "SquareRoot","VERIFY-sqrt-guid",     ("x",), ("y",)),
    ComponentSpec("abs",  "Absolute",  "VERIFY-abs-guid",      ("x",), ("y",)),
]

REGISTRY: dict[str, ComponentSpec] = {c.key: c for c in (_OPERATORS + _FUNCTIONS)}

# Well-known special components used as graph sources/sinks.
SLIDER = ComponentSpec(
    "slider", "Number Slider",
    "57da07bd-ecab-415d-9d86-af36d7073abc", (), ("value",), confirmed=True,
)
PANEL = ComponentSpec(
    "panel", "Panel",
    "59e0b89a-e487-49f8-bab8-b5bab16be14c", ("text",), (), confirmed=True,
)

# Map Python AST operator class names -> registry keys.
BINOP_MAP = {
    "Add": "add", "Sub": "sub", "Mult": "mul",
    "Div": "div", "Pow": "pow", "Mod": "mod",
}
# Map call targets (e.g. math.sin, sin) -> registry keys.
CALL_MAP = {
    "sin": "sin", "cos": "cos", "sqrt": "sqrt", "abs": "abs",
}


def get(key: str) -> ComponentSpec:
    try:
        return REGISTRY[key]
    except KeyError:
        raise KeyError(
            f"no Grasshopper component mapped for {key!r}. "
            f"Add it to the registry (see tools/harvest_components.py)."
        )


def unverified() -> list[str]:
    """Keys whose GUIDs still need confirming against a real install."""
    bad = [k for k, c in REGISTRY.items() if not c.confirmed or "VERIFY" in c.guid]
    for c in (SLIDER, PANEL):
        if not c.confirmed:
            bad.append(c.key)
    return bad
