# harvest_components.py
# -----------------------------------------------------------------------------
# Run this INSIDE Grasshopper (drop it in a GhPython / Python 3 Script component)
# to dump the authoritative display-name -> GUID table from YOUR installed
# components, including any third-party plugins. The output is PASTE-READY: copy
# the printed `GUIDS = { ... }` block and send it back, or paste the matching
# GUIDs straight into src/py2gh/components.py.
#
# This is the source of truth: hardcoded GUIDs can drift between versions and can
# never cover plugins, so harvesting from the live install is the robust path.
# -----------------------------------------------------------------------------
import Grasshopper as gh

server = gh.Instances.ComponentServer

# Every display name py2gh currently maps. Names must match Grasshopper's
# component display names exactly (mind the spaces, e.g. "Square Root").
wanted = {
    # arithmetic
    "Addition", "Subtraction", "Multiplication", "Division", "Power", "Modulus",
    "Negative", "Sine", "Cosine", "Square Root", "Absolute",
    # comparisons & boolean logic
    "Larger Than", "Smaller Than", "Equality",
    "Gate And", "Gate Or", "Gate Not",
    # geometry constructors & data
    "Construct Point", "Vector XYZ", "Merge",
    # callable geometry / utility components
    "Line", "PolyLine", "Divide Curve", "End Points", "Deconstruct",
    "Iso Curve", "Join Curves", "Offset Surface", "Pipe", "Solid Union",
    "Unit Z", "Cull Index",
    # sources / sinks
    "Number Slider", "Boolean Toggle", "Panel",
}

found = {}
for proxy in server.ObjectProxies:
    name = proxy.Desc.Name
    if name in wanted and name not in found:
        found[name] = str(proxy.Guid)

# Paste-ready: a Python dict literal, plus a report of anything not found.
print("# --- paste this back; py2gh fills the registry from it ---")
print("GUIDS = {")
for name in sorted(found):
    print('    %-18r: %r,' % (name, found[name]))
print("}")

missing = sorted(wanted - set(found))
if missing:
    print("\n# NOT FOUND on this install (check the exact display name / plugin):")
    for name in missing:
        print("#   " + name)

# If you add an output param named `table`, this also flows out of the component.
table = "\n".join("%s\t%s" % (n, g) for n, g in sorted(found.items()))
