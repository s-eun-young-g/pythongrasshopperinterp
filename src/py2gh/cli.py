"""Command-line entry point: `py2gh input.py -o out.ghx`."""

from __future__ import annotations

import argparse
import os
import sys

from . import __version__
from .analyzer import UnsupportedPython, analyze
from .components import unverified
from .emitter import emit


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
    parser.add_argument("input", nargs="?", help="Python source file to convert")
    parser.add_argument("-o", "--output", help="output .ghx path (default: alongside input)")
    parser.add_argument("--check-guids", action="store_true",
                        help="list component GUIDs that still need confirming, then exit")
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


if __name__ == "__main__":
    sys.exit(main())
