"""Reverse front end: a .ghx archive -> IR graph.

This is the inverse of emitter.py. It walks the GH_IO XML tree and rebuilds the
same `ir.Graph` the emitter consumes, so the rest of the toolchain (describe,
decompile) can work on any definition exported from Grasshopper -- not just ones
py2gh produced.

NOTE on `.gh` vs `.ghx`: a binary `.gh` and an XML `.ghx` are two serializations
of the *same* GH_IO data model. We read the XML form; to ingest a binary `.gh`,
open it in Grasshopper and `File > Save As` a `.ghx` first (one step), or read it
through GH_IO.dll. The structural walk below is identical either way.

WIRING (the inverse of emitter._wire_guid)
------------------------------------------
A downstream input cites a `Source` guid. That guid is:
  * a component's `param_output` InstanceGuid, or
  * a Number Slider / Panel's own node InstanceGuid (they *are* their output).
So we index every output by the guid a consumer would cite, then resolve each
input's Source guids against that index.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .components import PANEL, SLIDER
from .ir import Graph, InPort, Node, NodeKind, OutPort


# -- XML navigation helpers -------------------------------------------------

def _chunks(parent: ET.Element, name: str) -> list[ET.Element]:
    found = []
    for group in parent.findall("chunks"):
        for chunk in group.findall("chunk"):
            if chunk.get("name") == name:
                found.append(chunk)
    return found


def _chunk(parent: ET.Element, name: str) -> ET.Element | None:
    chunks = _chunks(parent, name)
    return chunks[0] if chunks else None


def _items(chunk: ET.Element) -> dict[str, str]:
    """name -> text for plain items (first wins; multi-valued names use _sources)."""
    out: dict[str, str] = {}
    items = chunk.find("items")
    if items is None:
        return out
    for item in items.findall("item"):
        out.setdefault(item.get("name"), (item.text or "").strip())
    return out


def _sources(chunk: ET.Element) -> list[str]:
    items = chunk.find("items")
    if items is None:
        return []
    return [(it.text or "").strip()
            for it in items.findall("item") if it.get("name") == "Source"]


def _pivot(chunk: ET.Element) -> tuple[float, float]:
    attrs = _chunk(chunk, "Attributes")
    if attrs is None:
        return (0.0, 0.0)
    items = attrs.find("items")
    if items is None:
        return (0.0, 0.0)
    for item in items.findall("item"):
        if item.get("name") == "Pivot":
            x = item.findtext("X", "0")
            y = item.findtext("Y", "0")
            return (float(x), float(y))
    return (0.0, 0.0)


def _to_float(text: str, default: float = 0.0) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


# -- the reader -------------------------------------------------------------

def read(ghx: str) -> Graph:
    """Parse a .ghx string into an IR Graph (preserving original GUIDs)."""
    root = ET.fromstring(ghx)
    definition = _chunk(root, "Definition")
    if definition is None:
        raise ValueError("not a Grasshopper archive: no <chunk name=\"Definition\">")
    objects = _chunk(definition, "DefinitionObjects")
    if objects is None:
        raise ValueError("archive has no DefinitionObjects chunk")

    graph = Graph()
    wire_index: dict[str, OutPort] = {}      # guid a consumer cites -> OutPort
    pending: list[tuple[InPort, list[str]]] = []

    for obj in _chunks(objects, "Object"):
        node = _read_object(obj, wire_index, pending)
        if node is not None:
            graph.nodes.append(node)

    # Second pass: resolve wires now that every output guid is indexed.
    for inp, source_guids in pending:
        for guid in source_guids:
            out = wire_index.get(guid)
            if out is not None:
                inp.connect(out)
    return graph


def _read_object(obj, wire_index, pending) -> Node | None:
    obj_items = _items(obj)
    ctype = obj_items.get("GUID", "")
    cname = obj_items.get("Name", "")
    container = _chunk(obj, "Container")
    if container is None:
        return None  # groups, scribbles, and other non-component objects
    cinfo = _items(container)
    iguid = cinfo.get("InstanceGuid", "")
    nick = cinfo.get("NickName", "")

    if ctype == SLIDER.guid:
        node = Node(NodeKind.SLIDER, cname, ctype, iguid, nickname=nick)
        slider = _chunk(container, "Slider")
        sinfo = _items(slider) if slider is not None else {}
        node.data = {
            "value": _to_float(sinfo.get("Value", "0")),
            "min": _to_float(sinfo.get("Min", "0")),
            "max": _to_float(sinfo.get("Max", "0")),
        }
        out = OutPort(node, "value", iguid)   # slider's wire guid is its own
        node.outputs.append(out)
        wire_index[iguid] = out

    elif ctype == PANEL.guid:
        node = Node(NodeKind.PANEL, cname, ctype, iguid, nickname=nick)
        node.data = {"text": cinfo.get("UserText", "")}
        inp = InPort(node, "text", iguid)
        node.inputs.append(inp)
        pending.append((inp, _sources(container)))

    else:
        node = Node(NodeKind.OP, cname, ctype, iguid, nickname=nick)
        for pin in _chunks(container, "param_input"):
            pinfo = _items(pin)
            inp = InPort(node, pinfo.get("Name", ""), pinfo.get("InstanceGuid", ""))
            node.inputs.append(inp)
            pending.append((inp, _sources(pin)))
        for pout in _chunks(container, "param_output"):
            pinfo = _items(pout)
            out = OutPort(node, pinfo.get("Name", ""), pinfo.get("InstanceGuid", ""))
            node.outputs.append(out)
            wire_index[out.instance_guid] = out

    node.pivot = _pivot(container)
    return node


def read_file(path: str) -> Graph:
    with open(path, "r", encoding="utf-8") as f:
        return read(f.read())
