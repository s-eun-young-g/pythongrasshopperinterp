"""Back end: IR graph -> .ghx (GH_IO XML archive).

The structure below is modeled byte-for-structure on a REAL modern Grasshopper
export (GH 0.9+, ArchiveVersion 0.2.2), not guessed. The details that actually
decide whether Rhino can open the file:

  * Items inside every chunk are written ALPHABETICALLY by name. GH_IO reads by
    name lookup so order is not strictly required, but matching real output
    removes a class of risk -- the renderer sorts items for us.

  * A wire is stored on the DOWNSTREAM input as a `Source` item whose value is
    the InstanceGuid of the UPSTREAM OUTPUT PARAMETER -- crucially NOT the
    upstream component's own guid. A Number Slider *is* a parameter, so its wire
    guid is its own InstanceGuid; an Addition component exposes a `param_output`
    chunk with its own InstanceGuid, and that is what downstream inputs cite.
    Getting this wrong silently breaks every component->component connection.

  * `Attributes` carries only `Bounds` + `Pivot` (panels add margins). Operator
    containers are minimal: Description, InstanceGuid, Name, NickName.

Type codes (from the same real file): gh_bool=1, gh_int32=3, gh_double=6,
gh_date=8, gh_guid=9, gh_string=10, gh_drawing_pointf=31, gh_drawing_rectanglef=35,
gh_drawing_color=36, gh_version=80.
"""

from __future__ import annotations

import datetime as _dt
from xml.sax.saxutils import escape

from .ir import Graph, Node, NodeKind, OutPort

_IND = "  "


# ---------------------------------------------------------------------------
# Archive builder. Items render alphabetically; chunks keep insertion order.
# ---------------------------------------------------------------------------

class Item:
    def __init__(self, name, type_name, type_code, value=None,
                 children=None, index=None):
        self.name = name
        self.type_name = type_name
        self.type_code = type_code
        self.value = value
        self.children = children
        self.index = index

    def render(self, depth: int) -> list[str]:
        pad = _IND * depth
        if self.index is not None:
            attrs = (f'name="{self.name}" index="{self.index}" '
                     f'type_name="{self.type_name}" type_code="{self.type_code}"')
        else:
            attrs = (f'name="{self.name}" '
                     f'type_name="{self.type_name}" type_code="{self.type_code}"')
        if self.children is not None:
            lines = [f"{pad}<item {attrs}>"]
            for k, v in self.children.items():
                lines.append(f"{pad}{_IND}<{k}>{v}</{k}>")
            lines.append(f"{pad}</item>")
            return lines
        text = "" if self.value is None else escape(str(self.value))
        return [f"{pad}<item {attrs}>{text}</item>"]


class Chunk:
    def __init__(self, name: str, index=None):
        self.name = name
        self.index = index
        self.items: list[Item] = []
        self.chunks: list["Chunk"] = []

    def add(self, *items: Item) -> "Chunk":
        self.items.extend(items)
        return self

    def chunk(self, c: "Chunk") -> "Chunk":
        self.chunks.append(c)
        return c

    def render(self, depth: int) -> list[str]:
        pad = _IND * depth
        attrs = f'name="{self.name}"'
        if self.index is not None:
            attrs += f' index="{self.index}"'
        lines = [f"{pad}<chunk {attrs}>",
                 f'{pad}{_IND}<items count="{len(self.items)}">']
        for it in sorted(self.items, key=lambda i: i.name):   # alphabetical
            lines += it.render(depth + 2)
        lines.append(f"{pad}{_IND}</items>")
        if self.chunks:
            lines.append(f'{pad}{_IND}<chunks count="{len(self.chunks)}">')
            for c in self.chunks:
                lines += c.render(depth + 2)
            lines.append(f"{pad}{_IND}</chunks>")
        lines.append(f"{pad}</chunk>")
        return lines


# typed-item helpers ------------------------------------------------------------

def _guid(name, value, index=None):
    return Item(name, "gh_guid", 9, value, index=index)

def _str(name, value):
    return Item(name, "gh_string", 10, value)

def _bool(name, value):
    return Item(name, "gh_bool", 1, "true" if value else "false")

def _int(name, value):
    return Item(name, "gh_int32", 3, int(value))

def _dbl(name, value):
    return Item(name, "gh_double", 6, repr(float(value)))

def _pointf(name, x, y):
    return Item(name, "gh_drawing_pointf", 31, children={"X": x, "Y": y})

def _rectf(name, x, y, w, h):
    return Item(name, "gh_drawing_rectanglef", 35,
                children={"X": x, "Y": y, "W": w, "H": h})


def _attributes(x, y, w, h) -> Chunk:
    c = Chunk("Attributes")
    c.add(_rectf("Bounds", x, y, w, h),
          _pointf("Pivot", x + w / 2.0, y + h / 2.0))
    return c


# ---------------------------------------------------------------------------
# Wiring: the guid a downstream input must cite to read this output.
# ---------------------------------------------------------------------------

def _wire_guid(out: OutPort) -> str:
    # A slider/param has no child output param -- it IS the output, so cite the
    # node. A component cites its param_output's own InstanceGuid.
    if out.node.kind in (NodeKind.SLIDER, NodeKind.PANEL):
        return out.node.instance_guid
    return out.instance_guid


# ---------------------------------------------------------------------------
# Layout.
# ---------------------------------------------------------------------------

def _layout(graph: Graph) -> None:
    depth: dict[int, int] = {}

    def d(node: Node) -> int:
        if id(node) in depth:
            return depth[id(node)]
        depth[id(node)] = 0
        srcs = [ip.source.node for ip in node.inputs if ip.source]
        depth[id(node)] = 1 + max((d(s) for s in srcs), default=-1)
        return depth[id(node)]

    for n in graph.nodes:
        d(n)
    rows: dict[int, int] = {}
    for n in graph.nodes:
        col = depth[id(n)]
        row = rows.get(col, 0)
        rows[col] = row + 1
        n.pivot = (120.0 + col * 220.0, 120.0 + row * 90.0)


# ---------------------------------------------------------------------------
# Per-node serialization (matches the real export).
# ---------------------------------------------------------------------------

def _param_input(ip, idx, px, py) -> Chunk:
    c = Chunk("param_input", index=idx)
    c.add(_str("Description", f"Input {ip.name}"),
          _guid("InstanceGuid", ip.instance_guid),
          _str("Name", ip.name),
          _str("NickName", ip.name),
          _bool("Optional", False))
    if ip.source is not None:
        c.add(_guid("Source", _wire_guid(ip.source), index=0),
              _int("SourceCount", 1))
    else:
        c.add(_int("SourceCount", 0))
    c.chunk(_attributes(px + 2.0, py + 2.0 + 20.0 * idx, 14.0, 20.0))
    return c


def _param_output(out: OutPort, out_name, idx, px, py, h) -> Chunk:
    c = Chunk("param_output", index=idx)
    c.add(_str("Description", "Result"),
          _guid("InstanceGuid", out.instance_guid),
          _str("Name", out_name),
          _str("NickName", out_name[:1] or "R"),
          _bool("Optional", False),
          _int("SourceCount", 0))
    c.chunk(_attributes(px + 46.0, py + 2.0, 17.0, max(20.0, h - 4.0)))
    return c


def _container_op(node: Node) -> Chunk:
    px, py = node.pivot
    h = max(44.0, 20.0 * max(len(node.inputs), 1) + 4.0)
    cont = Chunk("Container")
    cont.add(_str("Description", node.component_name),
             _guid("InstanceGuid", node.instance_guid),
             _str("Name", node.component_name),
             _str("NickName", node.nickname or node.component_name))
    cont.chunk(_attributes(px, py, 65.0, h))
    for i, ip in enumerate(node.inputs):
        cont.chunk(_param_input(ip, i, px, py))
    out_name = "Result"
    for i, op in enumerate(node.outputs):
        cont.chunk(_param_output(op, out_name, i, px, py, h))
    return cont


def _container_slider(node: Node) -> Chunk:
    px, py = node.pivot
    value = float(node.data.get("value", 0.0))
    cont = Chunk("Container")
    cont.add(_str("Description", "Numeric slider for single values"),
             _guid("InstanceGuid", node.instance_guid),
             _str("Name", node.component_name),
             _str("NickName", node.nickname or ""),
             _bool("Optional", False),
             _int("SourceCount", 0))
    cont.chunk(_attributes(px, py, 160.0, 20.0))
    s = Chunk("Slider")
    digits = 3
    s.add(_int("Digits", digits),
          _int("GripDisplay", 1),
          _int("Interval", 1),
          _dbl("Max", float(node.data.get("max", 10.0))),
          _dbl("Min", float(node.data.get("min", 0.0))),
          _dbl("Value", value))
    cont.chunk(s)
    return cont


def _container_panel(node: Node) -> Chunk:
    px, py = node.pivot
    ip = node.inputs[0]
    cont = Chunk("Container")
    cont.add(_str("Description", "A panel for custom notes and text values"),
             _guid("InstanceGuid", node.instance_guid),
             _str("Name", node.component_name),
             _str("NickName", node.nickname or ""),
             _bool("Optional", False),
             _dbl("ScrollRatio", 0.0),
             _str("UserText", ""))
    if ip.source is not None:
        cont.add(_guid("Source", _wire_guid(ip.source), index=0),
                 _int("SourceCount", 1))
    else:
        cont.add(_int("SourceCount", 0))
    a = Chunk("Attributes")
    a.add(_rectf("Bounds", px, py, 120.0, 60.0),
          _int("MarginLeft", 0), _int("MarginRight", 0), _int("MarginTop", 0),
          _pointf("Pivot", px + 60.0, py + 30.0))
    cont.chunk(a)
    p = Chunk("PanelProperties")
    p.add(Item("Colour", "gh_drawing_color", 36, children={"ARGB": "255;255;250;90"}),
          _bool("DrawIndices", True), _bool("DrawPaths", True),
          _bool("Multiline", True), _bool("Stream", False), _bool("Wrap", True))
    cont.chunk(p)
    return cont


def _object_chunk(node: Node, index: int) -> Chunk:
    obj = Chunk("Object", index=index)
    obj.add(_guid("GUID", node.component_guid),
            _str("Name", node.component_name))
    if node.kind is NodeKind.OP:
        obj.chunk(_container_op(node))
    elif node.kind is NodeKind.SLIDER:
        obj.chunk(_container_slider(node))
    elif node.kind is NodeKind.PANEL:
        obj.chunk(_container_panel(node))
    return obj


# ---------------------------------------------------------------------------
# Top-level assembly.
# ---------------------------------------------------------------------------

def _ticks(dt: _dt.datetime) -> int:
    return int((dt - _dt.datetime(1, 1, 1)).total_seconds() * 10_000_000)


def emit(graph: Graph, name: str = "py2gh.ghx") -> str:
    _layout(graph)
    now = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)

    definition = Chunk("Definition")
    definition.add(Item("plugin_version", "gh_version", 80,
                        children={"Major": 0, "Minor": 9, "Revision": 76}))

    header = Chunk("DefinitionHeader")
    header.add(_bool("HandleRhinoEvents", True),
               _bool("HandleHopperEvents", True),
               _str("Preview", "Shaded"))
    definition.chunk(header)

    props = Chunk("DefinitionProperties")
    props.add(_str("Name", name),
              _str("Description", "Generated by py2gh"),
              Item("Date", "gh_date", 8, _ticks(now)))
    definition.chunk(props)

    objects = Chunk("DefinitionObjects")
    objects.add(_int("ObjectCount", len(graph.nodes)))
    for i, node in enumerate(graph.nodes):
        objects.chunk(_object_chunk(node, i))
    definition.chunk(objects)

    lines = ['<?xml version="1.0" encoding="utf-8" standalone="yes"?>',
             '<Archive name="Root">',
             '  <!--Archive generated by py2gh-->',
             '  <items count="2">']
    lines += Item("ArchiveVersion", "gh_version", 80,
                  children={"Major": 0, "Minor": 2, "Revision": 2}).render(2)
    lines += Item("Created", "gh_date", 8, _ticks(now)).render(2)
    lines += ['  </items>', '  <chunks count="1">']
    lines += definition.render(2)
    lines += ['  </chunks>', '</Archive>', '']
    return "\n".join(lines)


def write(graph: Graph, path: str, name: str | None = None) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(emit(graph, name or path.split("/")[-1]))
