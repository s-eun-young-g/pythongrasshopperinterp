# A small parametric 2D truss, expressed natively (forward: py2gh mini_truss.py).
span = 10.0
closed = False

a = (0.0, 0.0, 0.0)
b = (span, 0.0, 0.0)

chord = line(a, b)
bays = divide_curve(chord, 5.0)
truss = polyline(bays, closed)
