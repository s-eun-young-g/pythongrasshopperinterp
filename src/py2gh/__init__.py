"""py2gh — convert Python source into a Grasshopper definition (.ghx).

Public API:
    analyze(source)        -> ir.Graph
    emit(graph, name)      -> str   (.ghx XML)
    write(graph, path)     -> None
    convert(source, name)  -> str   (analyze + emit in one call)
"""

from __future__ import annotations

from .analyzer import UnsupportedPython, analyze
from .emitter import emit, write
from .ir import Graph

__all__ = ["analyze", "emit", "write", "convert", "Graph", "UnsupportedPython"]

__version__ = "0.1.0"


def convert(source: str, name: str = "py2gh.ghx") -> str:
    """Analyze Python `source` and return the .ghx XML as a string."""
    return emit(analyze(source), name)
