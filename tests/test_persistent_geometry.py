"""Geometry-blob type decode + structured persistent geometry types."""

import base64
import os
import xml.etree.ElementTree as ET
import zlib

from py2gh import read
from py2gh.geometry import decode_geometry_type

TRUSS = os.path.join(os.path.dirname(__file__), "..", "examples", "truss2d.ghx")


def _make_blob(typename: str) -> str:
    """Build a blob shaped like GH's ON_Data: raw-deflate over a .NET stream that
    names a Rhino.Geometry type."""
    payload = (b"\x00\x01stuff..Rhino.Geometry." + typename.encode("ascii")
               + b"..WRhinoCommon, Version=8.0..archive3dm..")
    comp = zlib.compressobj(9, zlib.DEFLATED, -15)
    raw = comp.compress(payload) + comp.flush()
    return base64.b64encode(raw).decode("ascii")


def test_decode_geometry_type_from_synthetic_blob():
    assert decode_geometry_type(_make_blob("Brep")) == "Brep"
    assert decode_geometry_type(_make_blob("Curve")) == "Curve"


def test_decode_handles_garbage_gracefully():
    assert decode_geometry_type("not base64 @@@") is None
    assert decode_geometry_type(base64.b64encode(b"random").decode()) is None


def test_real_truss_blob_is_a_brep():
    raw = None
    for it in ET.parse(TRUSS).getroot().iter("item"):
        if it.get("type_name") == "gh_bytearray":
            raw = it.find("stream").text
            break
    assert raw is not None
    assert decode_geometry_type(raw) == "Brep"


def test_interval_persistent_is_decoded():
    g = read(open(TRUSS, encoding="utf-8").read())
    intervals = [ip.persistent for n in g.nodes for ip in n.inputs
                 if ip.persistent is not None and ip.persistent.kind == "interval"]
    assert intervals
    assert intervals[0].value == (0.0, 1.0)
