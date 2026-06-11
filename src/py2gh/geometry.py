"""Decode geometry that Grasshopper stores as a binary blob (gh_bytearray).

WHAT THE BLOB IS
----------------
When geometry is typed directly into a param (not wired), Grasshopper stores it
in PersistentData as a `gh_bytearray` named `ON_Data`. That byte array is, in
layers: base64  ->  raw DEFLATE  ->  a .NET-serialized RhinoCommon geometry
object whose payload is an `archive3dm` (OpenNURBS) buffer.

WHAT WE CAN AND CAN'T DO HEADLESS
---------------------------------
We can robustly read the object's *type* ("Brep", "Curve", "Surface", ...) from
the decompressed .NET stream with the standard library alone. We deliberately do
NOT try to reconstruct exact vertices: the inner buffer is a RhinoCommon goo
archive, not a standalone OpenNURBS `.3dm`, so `rhino3dm` can't decode it and a
faithful reconstruction needs Rhino / GH_IO. Reporting the type (instead of
"some bytes") is the honest, dependency-free win.
"""

from __future__ import annotations

import base64
import re
import zlib

# RhinoCommon serializes the type as a .NET assembly-qualified name; the
# `Rhino.Geometry.<Type>` token is stable and readable in the inflated stream.
_TYPE_RE = re.compile(rb"Rhino\.Geometry\.([A-Za-z0-9_]+)")


def decode_geometry_type(b64_text: str) -> str | None:
    """Return the geometry type stored in an ON_Data blob (e.g. "Brep"), or None
    if the bytes don't decode to a recognizable RhinoCommon object."""
    if not b64_text:
        return None
    try:
        raw = base64.b64decode(b64_text)
    except (ValueError, TypeError):
        return None
    data = _inflate(raw)
    if data is None:
        return None
    match = _TYPE_RE.search(data)
    return match.group(1).decode("ascii") if match else None


def _inflate(raw: bytes) -> bytes | None:
    """GH wraps the payload in raw DEFLATE; fall back to zlib/gzip just in case."""
    for wbits in (-15, 15, 31):
        try:
            return zlib.decompress(raw, wbits)
        except zlib.error:
            continue
    return None
