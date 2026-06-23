from __future__ import annotations

import ast
import operator
import re
from typing import Mapping


class FormulaError(ValueError):
    pass


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def normalize_formula(expression: str) -> str:
    expression = expression.strip().replace("×", "*").replace("÷", "/").replace("^", "**")
    if "=" in expression:
        expression = expression.split("=", 1)[1]
    expression = re.sub(r"\bV([1-7])t?\b", lambda match: f"V{match.group(1)}", expression, flags=re.I)
    return expression.strip()


def evaluate_formula(expression: str, values: Mapping[str, float | None]) -> float | None:
    normalized = normalize_formula(expression)
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Fórmula inválida: {expression}") from exc

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name) and re.fullmatch(r"V[1-7]", node.id, re.I):
            value = values.get(node.id.upper())
            if value is None:
                return None
            return float(value)
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            left, right = evaluate(node.left), evaluate(node.right)
            if left is None or right is None:
                return None
            try:
                return _BINARY_OPERATORS[type(node.op)](left, right)
            except ZeroDivisionError:
                return None
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            value = evaluate(node.operand)
            return None if value is None else _UNARY_OPERATORS[type(node.op)](value)
        raise FormulaError("La fórmula contiene una operación no permitida")

    result = evaluate(tree)
    return None if result is None else round(float(result), 6)
