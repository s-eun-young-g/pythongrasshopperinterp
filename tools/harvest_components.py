# harvest_components.py
# -----------------------------------------------------------------------------
# Run this INSIDE Grasshopper (drop it in a GhPython / Python 3 Script component)
# to dump the authoritative name -> GUID table from YOUR installed components,
# including any third-party plugins. Paste the relevant lines into
# src/py2gh/components.py so the converter emits GUIDs your Rhino can resolve.
#
# This is the source of truth: hardcoded GUIDs can drift between versions and can
# never cover plugins, so harvesting from the live install is the robust path.
# -----------------------------------------------------------------------------
import Grasshopper as gh

server = gh.Instances.ComponentServer

wanted = {
    "Addition", "Subtraction", "Multiplication", "Division", "Power", "Modulus",
    "Negative", "Sine", "Cosine", "Square Root", "Absolute",
    "Number Slider", "Panel",
}

rows = []
for proxy in server.ObjectProxies:
    name = proxy.Desc.Name
    if name in wanted:
        rows.append((name, str(proxy.Guid)))

rows.sort()
print("name -> guid")
for name, guid in rows:
    print('%-16s %s' % (name, guid))

# Also expose as a Grasshopper output if you add an output param named `table`.
table = "\n".join("%s\t%s" % r for r in rows)
