# Comparisons, booleans, and geometry all lower to Grasshopper components.
a = 2.0
b = 5.0

in_range = (a < b) and (b < 10.0)

origin = (0.0, 0.0, 0.0)
corner = (a, b, 0.0)
points = [origin, corner]
