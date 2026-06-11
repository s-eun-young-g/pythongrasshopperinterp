"""Command-line entry point.

Forward (default):  py2gh input.py [-o out.ghx]        Python -> .ghx
Reverse:            py2gh --describe   input.ghx        .ghx  -> description
                    py2gh --to-python  input.ghx [-o out.py]   .ghx -> Python
"""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .analyzer import UnsupportedPython, analyze
from .components import unverified
from .decompile import to_python
from .describe import describe
from .emitter import emit
from .reader import read


def _check_guids() -> int:
    bad = unverified()
    if not bad:
        print("All registered component GUIDs are confirmed.")
        return 0
    print("Unconfirmed component GUIDs (harvest with tools/harvest_components.py):")
    for key in bad:
        print(f"  - {key}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="py2gh",
        description="Convert Python source into a Grasshopper definition (.ghx).",
    )
    parser.add_argument("input", nargs="?",
                        help="input file: Python (.py) to convert, or .ghx for the reverse modes")
    parser.add_argument("-o", "--output", help="output path (default: alongside input)")
    parser.add_argument("--check-guids", action="store_true",
                        help="list component GUIDs that still need confirming, then exit")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--describe", action="store_true",
                      help="read a .ghx and print a structured description")
    mode.add_argument("--to-python", action="store_true",
                      help="read a .ghx and emit best-effort Python source")
    parser.add_argument("--version", action="version", version=f"py2gh {__version__}")
    args = parser.parse_args(argv)

    if args.check_guids:
        return _check_guids()

    if not args.input:
        parser.error("an input file is required (or use --check-guids)")

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError as exc:
        print(f"py2gh: cannot read {args.input}: {exc}", file=sys.stderr)
        return 2

    if args.describe or args.to_python:
        return _reverse(args, source)

    out_path = args.output or (os.path.splitext(args.input)[0] + ".ghx")
    name = os.path.basename(out_path)

    try:
        ghx = emit(analyze(source), name)
    except UnsupportedPython as exc:
        print(f"py2gh: {args.input}: {exc}", file=sys.stderr)
        return 1
    except SyntaxError as exc:
        print(f"py2gh: {args.input}: syntax error: {exc}", file=sys.stderr)
        return 1

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(ghx)
    print(f"py2gh: wrote {out_path}")
    return 0


def _reverse(args, source: str) -> int:
    """Handle --describe / --to-python (a .ghx -> text)."""
    try:
        graph = read(source)
    except Exception as exc:  # malformed / non-Grasshopper XML
        print(f"py2gh: {args.input}: cannot read .ghx: {exc}", file=sys.stderr)
        return 1

    text = describe(graph) if args.describe else to_python(graph)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"py2gh: wrote {args.output}")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
