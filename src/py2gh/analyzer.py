"""Front end: Python source -> IR graph.

The analyzer walks a Python AST and lowers the subset it understands into IR
nodes. It deliberately understands *only* what maps cleanly onto Grasshopper
components; anything else raises `UnsupportedPython` with a line number, rather
than silently producing a broken definition.

Supported (v0):
  * numeric literals                 -> Number Slider
  * names                            -> a wire from the value bound to that name
  * binary ops  + - * / ** %         -> Math operator components
  * unary minus                      -> negative-valued slider (literal) or
                                        a Negative component (expression)
  * calls  sin/cos/sqrt/abs          -> the corresponding maths component

A value that is assigned to a name but never read again is a *result*, and gets
a Panel attached so you can see it on the canvas.

Lowering rule of thumb: each Python expression compiles to exactly one OutPort
(the wire carrying its value). `_expr` returns that port; statements bind it to
a name.
"""

from __future__ import annotations

import ast
from dataclasses import replace

from . import components
from .ir import Graph, OutPort


class UnsupportedPython(Exception):
    """Raised for any Python construct the analyzer can't lower to Grasshopper."""

    def __init__(self, node: ast.AST, message: str):
        line = getattr(node, "lineno", "?")
        super().__init__(f"line {line}: {message}")


def _is_number(node: ast.AST) -> bool:
    return (isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool))


class _Analyzer:
    def __init__(self) -> None:
        self.graph = Graph()
        self.env: dict[str, OutPort] = {}
        self.reads: set[str] = set()
        self.assigned: list[str] = []   # names in assignment order (may repeat)

    # -- expressions --------------------------------------------------------
    def expr(self, node: ast.AST) -> OutPort:
        if _is_number(node):
            return self.graph.add_slider(node.value).out

        if isinstance(node, ast.Name):
            if node.id not in self.env:
                raise UnsupportedPython(node, f"name {node.id!r} used before assignment")
            self.reads.add(node.id)
            return self.env[node.id]

        if isinstance(node, ast.BinOp):
            return self._binop(node)

        if isinstance(node, ast.UnaryOp):
            return self._unaryop(node)

        if isinstance(node, ast.Call):
            return self._call(node)

        if isinstance(node, ast.Compare):
            return self._compare(node)

        if isinstance(node, ast.BoolOp):
            return self._boolop(node)

        if isinstance(node, ast.Tuple):
            return self._construct("point", node.elts, node)

        if isinstance(node, ast.List):
            return self._list(node)

        if isinstance(node, ast.Constant) and isinstance(node.value, bool):
            return self.graph.add_toggle(node.value).out

        raise UnsupportedPython(node, f"unsupported expression: {type(node).__name__}")

    def _binop(self, node: ast.BinOp) -> OutPort:
        op_name = type(node.op).__name__
        key = components.BINOP_MAP.get(op_name)
        if key is None:
            raise UnsupportedPython(node, f"unsupported binary operator: {op_name}")
        left = self.expr(node.left)
        right = self.expr(node.right)
        comp = self.graph.add_op(components.get(key))
        comp.inputs[0].connect(left)
        comp.inputs[1].connect(right)
        return comp.out

    def _unaryop(self, node: ast.UnaryOp) -> OutPort:
        if isinstance(node.op, ast.UAdd):
            return self.expr(node.operand)          # +x is a no-op
        if isinstance(node.op, ast.USub):
            # Fold a negated literal into a single negative-valued slider;
            # negate an expression with a Negative component.
            if _is_number(node.operand):
                return self.graph.add_slider(-node.operand.value).out
            operand = self.expr(node.operand)
            comp = self.graph.add_op(components.get("neg"))
            comp.inputs[0].connect(operand)
            return comp.out
        if isinstance(node.op, ast.Not):
            operand = self.expr(node.operand)
            comp = self.graph.add_op(components.get("not"))
            comp.inputs[0].connect(operand)
            return comp.out
        raise UnsupportedPython(node, f"unsupported unary operator: {type(node.op).__name__}")

    def _compare(self, node: ast.Compare) -> OutPort:
        if len(node.ops) != 1:
            raise UnsupportedPython(node, "chained comparisons (a < b < c) are not supported")
        op_name = type(node.ops[0]).__name__
        mapping = components.COMPARE_MAP.get(op_name)
        if mapping is None:
            raise UnsupportedPython(node, f"unsupported comparison: {op_name}")
        key, out_index = mapping
        left = self.expr(node.left)
        right = self.expr(node.comparators[0])
        comp = self.graph.add_op(components.get(key))
        comp.inputs[0].connect(left)
        comp.inputs[1].connect(right)
        return comp.outputs[out_index]

    def _boolop(self, node: ast.BoolOp) -> OutPort:
        key = components.BOOLOP_MAP[type(node.op).__name__]
        ports = [self.expr(v) for v in node.values]
        acc = ports[0]
        for port in ports[1:]:          # fold a and b and c -> and(and(a, b), c)
            comp = self.graph.add_op(components.get(key))
            comp.inputs[0].connect(acc)
            comp.inputs[1].connect(port)
            acc = comp.out
        return acc

    def _call(self, node: ast.Call) -> OutPort:
        name = _call_name(node.func)
        if name is None:
            raise UnsupportedPython(node, "unsupported call expression")

        # point(x, y[, z]) / vector(x, y[, z]) -> a geometry constructor.
        ctor = components.CONSTRUCTOR_MAP.get(name)
        if ctor is not None:
            if node.keywords:
                raise UnsupportedPython(node, f"{name}() does not accept keyword arguments")
            return self._construct(ctor, node.args, node)

        # Any callable component: maths (sin/cos/...) and geometry (line, ...).
        if name in components.CALLABLE_KEYS:
            if node.keywords:
                raise UnsupportedPython(node, f"{name}() does not accept keyword arguments")
            spec = components.get(name)
            if len(node.args) > len(spec.inputs):
                raise UnsupportedPython(
                    node, f"{name}() takes at most {len(spec.inputs)} argument(s), got {len(node.args)}")
            comp = self.graph.add_op(spec)
            for arg_node, inp in zip(node.args, comp.inputs):
                inp.connect(self.expr(arg_node))
            return comp.out

        raise UnsupportedPython(node, f"unsupported call: {name}()")

    def _construct(self, key: str, elts: list[ast.AST], node: ast.AST) -> OutPort:
        """Build a Construct Point / Vector XYZ from 2 or 3 coordinates,
        padding a missing Z with a zero slider."""
        if not 2 <= len(elts) <= 3:
            raise UnsupportedPython(
                node, f"{key} needs 2 or 3 coordinates, got {len(elts)}")
        coords = [self.expr(e) for e in elts]
        while len(coords) < 3:
            coords.append(self.graph.add_slider(0.0).out)
        comp = self.graph.add_op(components.get(key))
        for port, dst in zip(coords, comp.inputs):
            dst.connect(port)
        return comp.out

    def _list(self, node: ast.List) -> OutPort:
        """A list literal becomes a Merge component collecting every item into
        one output stream (a Grasshopper list)."""
        if not node.elts:
            raise UnsupportedPython(node, "empty list has nothing to merge")
        items = [self.expr(e) for e in node.elts]
        spec = replace(components.get("merge"),
                       inputs=tuple(f"D{i + 1}" for i in range(len(items))))
        comp = self.graph.add_op(spec)
        for port, dst in zip(items, comp.inputs):
            dst.connect(port)
        return comp.out

    # -- statements ---------------------------------------------------------
    def stmt(self, node: ast.stmt) -> None:
        # Skip module/function docstrings and bare string expressions.
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            return

        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                raise UnsupportedPython(node, "only single-name assignment is supported")
            self._assign(node.targets[0].id, node.value)
            return

        raise UnsupportedPython(node, f"unsupported statement: {type(node).__name__}")

    def _assign(self, name: str, value: ast.AST) -> None:
        # A literal assigned directly to a name becomes a *named* slider, so the
        # canvas shows `a`, `b`, ... rather than `const1`, `const2`.
        if _is_number(value):
            port = self.graph.add_slider(value.value, nickname=name).out
        elif isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.USub) \
                and _is_number(value.operand):
            port = self.graph.add_slider(-value.operand.value, nickname=name).out
        elif isinstance(value, ast.Constant) and isinstance(value.value, bool):
            port = self.graph.add_toggle(value.value, nickname=name).out
        else:
            port = self.expr(value)
        self.env[name] = port
        self.assigned.append(name)

    # -- finalize -----------------------------------------------------------
    def attach_panels(self) -> None:
        """A name assigned but never read again is a result; show it on a Panel."""
        seen: set[str] = set()
        for name in self.assigned:
            if name in seen or name in self.reads:
                continue
            seen.add(name)
            panel = self.graph.add_panel(nickname=name)
            panel.inputs[0].connect(self.env[name])


def analyze(source: str) -> Graph:
    """Compile Python source text into an IR Graph."""
    tree = ast.parse(source)
    analyzer = _Analyzer()
    for stmt in tree.body:
        analyzer.stmt(stmt)
    analyzer.attach_panels()
    return analyzer.graph


def _call_name(func: ast.AST) -> str | None:
    """Resolve sin / math.sin / np.sin -> 'sin' (the trailing attribute/name)."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None
