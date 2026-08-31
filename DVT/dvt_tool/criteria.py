"""Safe evaluator for `pass_criteria` expressions.

Grammar (what the catalog actually uses):
    a AND b, a OR b, NOT a, (…)
    x == y, x != y, x < y, x <= y, x > y, x >= y
    + - * /  on numbers
    abs(x), max(a, b, …), min(a, b, …)
    identifiers = data fields;  dotted names = catalog thresholds
    (led_temperature_thresholds.working_limit);  literals: numbers, 'strings',
    true/false/null

No Python eval: the expression is parsed by `ast` and only the node types
above are executed. Result:
    (verdict, detail)  verdict ∈ {"PASS", "FAIL", "BLOCKED"}
BLOCKED = a referenced field is missing or a referenced threshold is null
(e.g. protective_shutdown not yet decided) — never silently PASS.
"""

from __future__ import annotations

import ast
import re
from typing import Any, Mapping


class CriteriaError(Exception):
    pass


class _Missing(Exception):
    def __init__(self, name):
        super().__init__(name)
        self.name = name


_ALLOWED_FUNCS = {"abs": abs, "max": max, "min": min}


def _normalise(expr: str) -> str:
    e = " ".join(expr.split())
    e = re.sub(r"\bAND\b", " and ", e)
    e = re.sub(r"\bOR\b", " or ", e)
    e = re.sub(r"\bNOT\b", " not ", e)
    e = re.sub(r"\btrue\b", "True", e)
    e = re.sub(r"\bfalse\b", "False", e)
    e = re.sub(r"\bnull\b", "None", e)
    return e


def referenced_names(expr: str) -> set[str]:
    tree = ast.parse(_normalise(expr), mode="eval")
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in _ALLOWED_FUNCS and node.id not in ("True", "False", "None"):
            names.add(node.id)
    return names


class _Evaluator(ast.NodeVisitor):
    def __init__(self, values: Mapping[str, Any], thresholds: Mapping[str, Any]):
        self.values, self.thresholds = values, thresholds

    def visit_Expression(self, n): return self.visit(n.body)

    def visit_BoolOp(self, n):
        vals = [self.visit(v) for v in n.values]
        return all(vals) if isinstance(n.op, ast.And) else any(vals)

    def visit_UnaryOp(self, n):
        v = self.visit(n.operand)
        if isinstance(n.op, ast.Not): return not v
        if isinstance(n.op, ast.USub): return -v
        raise CriteriaError("unsupported unary operator")

    def visit_BinOp(self, n):
        a, b = self.visit(n.left), self.visit(n.right)
        if isinstance(n.op, ast.Add): return a + b
        if isinstance(n.op, ast.Sub): return a - b
        if isinstance(n.op, ast.Mult): return a * b
        if isinstance(n.op, ast.Div): return a / b
        raise CriteriaError("unsupported operator")

    def visit_Compare(self, n):
        left = self.visit(n.left)
        for op, comp in zip(n.ops, n.comparators):
            right = self.visit(comp)
            ok = {ast.Eq: left == right, ast.NotEq: left != right, ast.Lt: left < right,
                  ast.LtE: left <= right, ast.Gt: left > right, ast.GtE: left >= right}.get(type(op))
            if ok is None:
                raise CriteriaError("unsupported comparison")
            if not ok:
                return False
            left = right
        return True

    def visit_Call(self, n):
        if not isinstance(n.func, ast.Name) or n.func.id not in _ALLOWED_FUNCS:
            raise CriteriaError("only abs/max/min may be called")
        return _ALLOWED_FUNCS[n.func.id](*[self.visit(a) for a in n.args])

    def visit_Constant(self, n): return n.value

    def visit_Name(self, n):
        if n.id in ("True", "False", "None"):
            return {"True": True, "False": False, "None": None}[n.id]
        if n.id not in self.values or self.values[n.id] is None:
            raise _Missing(n.id)
        return self.values[n.id]

    def visit_Attribute(self, n):
        parts = []
        cur = n
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr); cur = cur.value
        if not isinstance(cur, ast.Name):
            raise CriteriaError("bad threshold reference")
        parts.append(cur.id)
        path = ".".join(reversed(parts))
        node: Any = self.thresholds
        for p in reversed(parts):
            node = node.get(p) if isinstance(node, Mapping) else None
        if node is None:
            raise _Missing(path)
        return node

    def generic_visit(self, n):
        raise CriteriaError(f"unsupported syntax: {type(n).__name__}")


def evaluate(expr: str, values: Mapping[str, Any], thresholds: Mapping[str, Any] | None = None) -> tuple[str, str]:
    """Returns (verdict, detail). Never raises on missing data — that is BLOCKED."""
    try:
        tree = ast.parse(_normalise(expr), mode="eval")
        result = _Evaluator(values, thresholds or {}).visit(tree)
    except _Missing as m:
        return "BLOCKED", f"missing value: {m.name}"
    except SyntaxError as e:
        raise CriteriaError(f"cannot parse pass_criteria: {e}")
    except (TypeError, ValueError, ZeroDivisionError) as e:
        return "BLOCKED", f"cannot evaluate: {e}"
    return ("PASS" if bool(result) else "FAIL"), ""
