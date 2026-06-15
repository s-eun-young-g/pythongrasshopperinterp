"""py2gh - convert Python source into a Grasshopper definition (.ghx).

Public API:
    analyze(source)        -> ir.Graph
    emit(graph, name)      -> str   (.ghx XML)
    write(graph, path)     -> None
    convert(source, name)  -> str   (analyze + emit in one call)
"""

from __future__ import annotations

from .analyzer import UnsupportedPython, analyze
from .decompile import to_python
from .describe import describe
from .emitter import emit, write
from .ir import Graph
from .reader import read, read_file

__all__ = [
    "analyze", "emit", "write", "convert", "Graph", "UnsupportedPython",
    "read", "read_file", "describe", "to_python", "describe_ghx", "decompile_ghx",
]

__version__ = "0.2.0"


def convert(source: str, name: str = "py2gh.ghx") -> str:
    """Analyze Python `source` and return the .ghx XML as a string."""
    return emit(analyze(source), name)


def describe_ghx(ghx: str) -> str:
    """Read a .ghx string and return a human-readable description."""
    return describe(read(ghx))


def decompile_ghx(ghx: str) -> str:
    """Read a .ghx string and return best-effort Python source."""
    return to_python(read(ghx))
