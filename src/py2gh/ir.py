"""Intermediate representation: the graph that sits between the Python analyzer
and the .ghx emitter.

WHY AN IR AT ALL
----------------
The IR is the seam the whole project pivots on (see README). It models a
Grasshopper document as a plain directed graph of *nodes* (components) connected
through *ports*, with zero knowledge of either Python syntax or .ghx XML. The
analyzer's only job is to build one of these; the emitter's only job is to
serialize one. Neither end knows about the other, so a new source language or a
new output format plugs in without touching the middle.

WHAT THE EMITTER REQUIRES (the contract)
----------------------------------------
emitter.py reads exactly these fields, so they are the public API of this module:

  Graph.nodes                      ordered list of Node
  Node.kind                        NodeKind.{OP, SLIDER, PANEL}
  Node.component_name / .component_guid
  Node.instance_guid               unique per node
  Node.nickname                    str ("" means "fall back to a default")
  Node.inputs  -> list[InPort]
  Node.outputs -> list[OutPort]
  Node.pivot                       (x, y); filled in by the emitter's layout pass
  Node.data                        dict; sliders read value/min/max from here
  InPort.name / .instance_guid / .source(OutPort | None)
  OutPort.node / .name / .instance_guid

Everything else here (builder methods, connect helpers) exists to make the
analyzer pleasant to write and to keep GUID allocation in one place.

GUID ALLOCATION
---------------
Grasshopper uses random GUIDs; we mint deterministic ones (uuid.UUID(int=n))
per graph. They are still globally-unique-enough for a single document and,
being deterministic, make the output reproducible and testable. Grasshopper
resolves objects by GUID equality, not by value, so any unique set works.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum

from .components import PANEL, SLIDER, TOGGLE, ComponentSpec


class NodeKind(Enum):
    OP = "op"          # a regular component with input/output params
    SLIDER = "slider"  # a Number Slider (a source; no inputs)
    PANEL = "panel"    # a Panel (a sink; one text input, no outputs)
    TOGGLE = "toggle"  # a Boolean Toggle (a boolean source; no inputs)


@dataclass
class Internal:
    """A value typed into an unwired input and stored in the .ghx as
    PersistentData. `value` is a Python scalar (float/int/bool/str) for simple
    types; for geometry/plane/etc. it is None and `kind` names the GH type
    (e.g. "gh_bytearray"), since those need OpenNURBS to decode."""
    kind: str
    value: object = None
    count: int = 1   # how many items were stored (a list input may hold several)


@dataclass
class OutPort:
    """An output parameter of a node. Downstream inputs cite its guid to wire."""
    node: "Node"
    name: str
    instance_guid: str


@dataclass
class InPort:
    """An input parameter. `source` is the first upstream OutPort feeding it (what
    the emitter writes); `sources` holds all of them, since a real Grasshopper
    input can be wired to several outputs at once (e.g. a list collected from
    many components). Forward construction connects exactly one; the reader may
    connect many."""
    node: "Node"
    name: str
    instance_guid: str
    source: OutPort | None = None
    sources: list[OutPort] = field(default_factory=list)
    persistent: "Internal | None" = None   # typed-in value when unwired

    def connect(self, out: OutPort) -> None:
        if self.source is None:
            self.source = out
        self.sources.append(out)


@dataclass
class Node:
    kind: NodeKind
    component_name: str
    component_guid: str
    instance_guid: str
    nickname: str = ""
    inputs: list[InPort] = field(default_factory=list)
    outputs: list[OutPort] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    pivot: tuple[float, float] = (0.0, 0.0)

    @property
    def out(self) -> OutPort:
        """Convenience for the common single-output case."""
        return self.outputs[0]


class Graph:
    """A buildable Grasshopper document. Use the add_* helpers from the analyzer;
    they allocate GUIDs and wire ports consistently."""

    def __init__(self) -> None:
        self.nodes: list[Node] = []
        self._guid_counter = 0
        self._slider_count = 0

    # -- guid minting -------------------------------------------------------
    def new_guid(self) -> str:
        self._guid_counter += 1
        return str(uuid.UUID(int=self._guid_counter))

    # -- node builders ------------------------------------------------------
    def _register(self, node: Node) -> Node:
        self.nodes.append(node)
        return node

    def add_op(self, spec: ComponentSpec, nickname: str = "") -> Node:
        """Add a component from a registry spec, materializing its ports."""
        node = Node(NodeKind.OP, spec.name, spec.guid, self.new_guid(),
                    nickname=nickname)
        for name in spec.inputs:
            node.inputs.append(InPort(node, name, self.new_guid()))
        for name in spec.outputs:
            node.outputs.append(OutPort(node, name, self.new_guid()))
        return self._register(node)

    def add_slider(self, value: float, nickname: str | None = None) -> Node:
        """Add a Number Slider. Range auto-brackets the value (0..10 by default,
        widened if the value falls outside). An unnamed slider gets the
        `const{n}` nickname Grasshopper users will recognize as a literal."""
        self._slider_count += 1
        if nickname is None:
            nickname = f"const{self._slider_count}"
        node = Node(NodeKind.SLIDER, SLIDER.name, SLIDER.guid, self.new_guid(),
                    nickname=nickname)
        node.outputs.append(OutPort(node, "value", self.new_guid()))
        node.data = {
            "value": float(value),
            "min": min(0.0, float(value)),
            "max": max(10.0, float(value)),
        }
        return self._register(node)

    def add_toggle(self, value: bool, nickname: str = "") -> Node:
        """Add a Boolean Toggle (a True/False source)."""
        node = Node(NodeKind.TOGGLE, TOGGLE.name, TOGGLE.guid, self.new_guid(),
                    nickname=nickname)
        node.outputs.append(OutPort(node, "value", self.new_guid()))
        node.data = {"value": bool(value)}
        return self._register(node)

    def add_panel(self, nickname: str = "") -> Node:
        """Add a Panel sink with its single text input."""
        node = Node(NodeKind.PANEL, PANEL.name, PANEL.guid, self.new_guid(),
                    nickname=nickname)
        node.inputs.append(InPort(node, "text", self.new_guid()))
        return self._register(node)

    # -- wiring -------------------------------------------------------------
    @staticmethod
    def connect(out: OutPort, dst: InPort) -> None:
        dst.connect(out)
