"""IR graph -> best-effort Python source.

The inverse of analyzer.py. Components that have a native Python meaning
(arithmetic, comparisons, booleans, point/vector/list constructors) are rendered
back into ordinary Python; anything else becomes a `gh("Component Name", ...)`
placeholder call with a comment, so the output is always a complete, readable
program even when parts of the definition can't be lowered.

This is necessarily lossy: a Grasshopper definition is a richer object than a
Python expression graph. The goal is a faithful, runnable-where-possible
transcription, not a guarantee of executable equivalence.
"""

from __future__ import annotations

import keyword
from collections import defaultdict

from . import components
from .ir import Graph, Node, NodeKind, OutPort

# -- reverse mappings, derived from the same registry the analyzer uses ------

NAME_TO_KEY: dict[str, str] = {spec.name: spec.key for spec in components.REGISTRY.values()}

_BINOP_SYMBOL = {"add": "+", "sub": "-", "mul": "*", "div": "/", "pow": "**", "mod": "%"}
_FUNC_NAME = {"sin": "sin", "cos": "cos", "sqrt": "sqrt", "abs": "abs"}
# (registry key, consumed output index) -> Python comparison operator
_COMPARE_SYMBOL = {
    ("smaller", 0): "<", ("smaller", 1): "<=",
    ("larger", 0): ">", ("larger", 1): ">=",
    ("equal", 0): "==", ("equal", 1): "!=",
}
_BOOL_KEYWORD = {"and": "and", "or": "or"}

# Names describe.py uses to tell which components will decompile natively.
KNOWN_NAMES = set(NAME_TO_KEY)


def _valid_ident(name: str) -> bool:
    return bool(name) and name.isidentifier() and not keyword.iskeyword(name)


def _fmt_number(value: float) -> str:
    f = float(value)
    return f"{f:.1f}" if f == int(f) else repr(f)


def to_python(graph: Graph) -> str:
    panels = [n for n in graph.nodes if n.kind is NodeKind.PANEL]

    consumers: dict[int, list[Node]] = defaultdict(list)
    for node in graph.nodes:
        for inp in node.inputs:
            for src in inp.sources:
                consumers[id(src.node)].append(node)

    node_var: dict[int, str] = {}
    used: set[str] = set()
    inlined_panels: set[int] = set()

    def claim(name: str) -> str:
        base = name
        i = 2
        while name in used:
            name = f"{base}_{i}"
            i += 1
        used.add(name)
        return name

    # 1) Number sliders become named literals.
    counter = {"slider": 0}
    for node in graph.nodes:
        if node.kind is NodeKind.SLIDER:
            if _valid_ident(node.nickname):
                node_var[id(node)] = claim(node.nickname)
            else:
                counter["slider"] += 1
                node_var[id(node)] = claim(f"v{counter['slider']}")

    # 2) An op feeding exactly one panel takes that panel's name (so the result
    #    reads `area = a + b` instead of a throwaway temp plus a panel line).
    for p in panels:
        src = p.inputs[0].source if p.inputs else None
        if src is None:
            continue
        op = src.node
        if op.kind is NodeKind.OP and consumers[id(op)] == [p] and _valid_ident(p.nickname):
            node_var[id(op)] = claim(p.nickname)
            inlined_panels.add(id(p))

    # 3) Remaining ops get temporaries.
    tmp = 0
    for node in graph.nodes:
        if node.kind is NodeKind.OP and id(node) not in node_var:
            tmp += 1
            node_var[id(node)] = claim(f"t{tmp}")

    # Topological order: every node after the nodes feeding it.
    order: list[Node] = []
    seen: set[int] = set()

    def visit(node: Node) -> None:
        if id(node) in seen:
            return
        seen.add(id(node))
        for inp in node.inputs:
            for src in inp.sources:
                visit(src.node)
        order.append(node)

    for node in graph.nodes:
        visit(node)

    def ref(out: OutPort | None) -> str:
        return node_var.get(id(out.node), "None") if out is not None else "None"

    def used_output_index(node: Node) -> int:
        for consumer in graph.nodes:
            for inp in consumer.inputs:
                for src in inp.sources:
                    if src.node is node:
                        return node.outputs.index(src)
        return 0

    lines: list[str] = []
    for node in order:
        if node.kind is NodeKind.SLIDER:
            lines.append(f"{node_var[id(node)]} = {_fmt_number(node.data.get('value', 0.0))}")
        elif node.kind is NodeKind.OP:
            lines.append(f"{node_var[id(node)]} = {_render_op(node, ref, used_output_index)}")
        elif node.kind is NodeKind.PANEL and id(node) not in inlined_panels:
            src = node.inputs[0].source if node.inputs else None
            target = node.nickname if _valid_ident(node.nickname) else None
            if target:
                lines.append(f"{claim(target)} = {ref(src)}")
            else:
                lines.append(f"# output panel <- {ref(src)}")

    return "\n".join(lines) + ("\n" if lines else "")


def _render_op(node: Node, ref, used_output_index) -> str:
    key = NAME_TO_KEY.get(node.component_name)
    a = ref(node.inputs[0].source) if node.inputs else "None"
    b = ref(node.inputs[1].source) if len(node.inputs) > 1 else "None"

    if key in _BINOP_SYMBOL:
        return f"({a} {_BINOP_SYMBOL[key]} {b})"
    if key == "neg":
        return f"(-{a})"
    if key in _FUNC_NAME:
        return f"{_FUNC_NAME[key]}({a})"
    if key in ("smaller", "larger", "equal"):
        sym = _COMPARE_SYMBOL[(key, used_output_index(node))]
        return f"({a} {sym} {b})"
    if key in _BOOL_KEYWORD:
        return f"({a} {_BOOL_KEYWORD[key]} {b})"
    if key == "not":
        return f"(not {a})"
    if key in ("point", "vector"):
        coords = ", ".join(ref(ip.source) for ip in node.inputs)
        return f"({coords})" if key == "point" else f"vector({coords})"
    if key == "merge":
        items = ", ".join(ref(ip.source) for ip in node.inputs)
        return f"[{items}]"

    # No native mapping: emit a placeholder call so the program stays complete.
    args = ", ".join(ref(ip.source) for ip in node.inputs)
    return f'gh("{node.component_name}", {args})  # component has no native Python form'
