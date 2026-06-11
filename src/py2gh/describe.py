"""IR graph -> human-readable description.

Turns any definition (read from a .ghx) into a plain-text inventory: the
parametric inputs and their ranges, the operations and how they're wired, any
geometry, and the outputs. This works on *any* component, mapped or not, so it
is the always-available answer to "what is in this definition?".
"""

from __future__ import annotations

from .ir import Graph, Node, NodeKind, OutPort

_GEOMETRY_HINTS = (
    "Point", "Vector", "Line", "Curve", "Polyline", "Mesh", "Surface", "Brep",
    "Circle", "Arc", "Rectangle", "Plane", "Box", "Sphere", "Vertices",
)


def _is_geometry(name: str) -> bool:
    return any(h.lower() in name.lower() for h in _GEOMETRY_HINTS)


def describe(graph: Graph) -> str:
    sliders = [n for n in graph.nodes if n.kind is NodeKind.SLIDER]
    panels = [n for n in graph.nodes if n.kind is NodeKind.PANEL]
    ops = [n for n in graph.nodes if n.kind is NodeKind.OP]

    op_index = {id(n): i + 1 for i, n in enumerate(ops)}

    def label(node: Node) -> str:
        if node.kind is NodeKind.OP:
            return f"[{op_index[id(node)]}]"
        return node.nickname or node.component_name or "?"

    def src_label(out: OutPort | None) -> str:
        if out is None:
            return "—"
        node = out.node
        if node.kind is NodeKind.OP:
            return f"[{op_index[id(node)]}] {node.component_name}"
        return node.nickname or node.component_name

    lines: list[str] = []
    lines.append("py2gh — definition description")
    lines.append("=" * 32)
    lines.append(
        f"Objects: {len(graph.nodes)}  "
        f"(sliders: {len(sliders)}, operations: {len(ops)}, panels: {len(panels)})"
    )
    lines.append("")

    lines.append("Parametric inputs (Number Sliders):")
    if sliders:
        width = max(len(s.nickname or "const") for s in sliders)
        for s in sliders:
            name = (s.nickname or "const").ljust(width)
            v = s.data.get("value", 0.0)
            lo = s.data.get("min", 0.0)
            hi = s.data.get("max", 0.0)
            lines.append(f"  {name} = {v:<8g} [{lo:g} .. {hi:g}]")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("Operations:")
    if ops:
        for n in ops:
            wired = "  ".join(
                f"{ip.name}={src_label(ip.source)}" for ip in n.inputs
            ) or "(no inputs)"
            tag = "  [geometry]" if _is_geometry(n.component_name) else ""
            lines.append(f"  {label(n)} {n.component_name}{tag}")
            lines.append(f"      {wired}")
    else:
        lines.append("  (none)")
    lines.append("")

    geo = [n for n in ops if _is_geometry(n.component_name)]
    lines.append("Geometry / shapes:")
    if geo:
        for n in geo:
            lines.append(f"  {label(n)} {n.component_name}")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("Outputs (Panels):")
    if panels:
        for p in panels:
            src = p.inputs[0].source if p.inputs else None
            name = p.nickname or "panel"
            lines.append(f"  {name}  <-  {src_label(src)}")
    else:
        lines.append("  (none)")

    # Flag components that have no native Python mapping.
    from .decompile import KNOWN_NAMES  # local import avoids a cycle at import time
    unknown = sorted({n.component_name for n in ops
                      if n.component_name not in KNOWN_NAMES})
    if unknown:
        lines.append("")
        lines.append("Components without a native Python mapping "
                     "(emitted as gh(...) on decompile):")
        for name in unknown:
            lines.append(f"  - {name}")

    return "\n".join(lines) + "\n"
