"""Restricted interpreter for generated entry-filter expressions (Phase 2 codegen safety).

A filter is a single PURE boolean expression over a whitelisted set of names
(no imports, calls, attribute access, subscripts, or comprehensions). The
expression is parsed to an AST, structurally validated against a node whitelist,
and then INTERPRETED by an explicit recursive evaluator — there is deliberately
NO eval()/exec()/compile()-to-code path, so generated code can never reach the
Python interpreter, loop, or do IO. This is the safety boundary that lets the
loop autonomously test generated filters in the isolated lab.

    f = compile_filter("imbalance >= 0.35 and not divergence_bullish")
    f({"imbalance": 0.4, "divergence_bullish": False, ...})  -> True
"""
from __future__ import annotations

import ast
import operator

# Names a filter may reference. Anything else -> Rejection.
ALLOWED_NAMES = {
    "imbalance", "buy_ratio", "trade_count", "cvd_slope", "large_trade_bias",
    "divergence_bullish", "divergence_bearish", "hour", "price", "spread_pct",
}

_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Mod: operator.mod,
}
_CMPOPS = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
    ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
}


class Rejection(Exception):
    """Raised when a filter expression is unsafe or malformed."""


def _eval(node: ast.AST, env: dict):
    if isinstance(node, ast.Expression):
        return _eval(node.body, env)
    if isinstance(node, ast.BoolOp):
        vals = [_eval(v, env) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(vals)
        return any(vals)  # ast.Or
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, env)
        if isinstance(node.op, ast.Not):
            return not v
        if isinstance(node.op, ast.USub):
            return -v
        if isinstance(node.op, ast.UAdd):
            return +v
        raise Rejection(f"disallowed unary op: {type(node.op).__name__}")
    if isinstance(node, ast.BinOp):
        fn = _BINOPS.get(type(node.op))
        if fn is None:
            raise Rejection(f"disallowed binary op: {type(node.op).__name__}")
        right = _eval(node.right, env)
        if isinstance(node.op, (ast.Div, ast.Mod)) and right == 0:
            return 0  # safe: never raise inside a filter
        return fn(_eval(node.left, env), right)
    if isinstance(node, ast.Compare):
        left = _eval(node.left, env)
        for op, comparator in zip(node.ops, node.comparators):
            fn = _CMPOPS.get(type(op))
            if fn is None:
                raise Rejection(f"disallowed comparison: {type(op).__name__}")
            right = _eval(comparator, env)
            if not fn(left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Name):
        if node.id not in ALLOWED_NAMES:
            raise Rejection(f"unknown name: {node.id!r}")
        return env.get(node.id, 0)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, bool)):
            return node.value
        raise Rejection(f"only numeric/bool constants allowed, got {node.value!r}")
    raise Rejection(f"disallowed syntax: {type(node).__name__}")


def _validate(tree: ast.AST) -> None:
    """Reject unsafe nodes up front so compile_filter fails fast on bad codegen."""
    allowed = (
        ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
        ast.USub, ast.UAdd, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div,
        ast.Mod, ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt,
        ast.GtE, ast.Name, ast.Load, ast.Constant,
    )
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise Rejection(f"disallowed syntax: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in ALLOWED_NAMES:
            raise Rejection(f"unknown name: {node.id!r}")
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, bool)):
            raise Rejection(f"only numeric/bool constants allowed, got {node.value!r}")


def compile_filter(code: str):
    """Return a callable(ctx: dict) -> bool, or raise Rejection. Missing ctx keys
    default to 0 (the evaluator always supplies the full whitelist anyway)."""
    if not isinstance(code, str) or not code.strip():
        raise Rejection("empty filter")
    try:
        tree = ast.parse(code.strip(), mode="eval")
    except SyntaxError as e:
        raise Rejection(f"syntax error: {e}")
    _validate(tree)  # fail fast; _eval re-checks defensively

    def _fn(ctx: dict) -> bool:
        return bool(_eval(tree, ctx))

    return _fn
