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
        raise UnsupportedPython(node, f"unsupported unary operator: {type(node.op).__name__}")

    def _call(self, node: ast.Call) -> OutPort:
        name = _call_name(node.func)
        key = components.CALL_MAP.get(name) if name else None
        if key is None:
            raise UnsupportedPython(node, f"unsupported call: {name or '<expr>'}()")
        if len(node.args) != 1 or node.keywords:
            raise UnsupportedPython(node, f"{name}() expects exactly one positional argument")
        arg = self.expr(node.args[0])
        comp = self.graph.add_op(components.get(key))
        comp.inputs[0].connect(arg)
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
