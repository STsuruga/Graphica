"""利用者が入力した式を eval / exec を使わずに評価する(AST を辿り、許した構文だけ通す)。

使えるのは数値・変数・四則演算・べき乗・剰余・比較・and / or / not(要素ごとの & / | / ~)と許した関数。
列の計算では ALLOWED_SERIES_METHODS のメソッド(A.mean()、A.rolling(5).mean() など)も使える。
属性の任意呼び出し・添字・lambda・内包表記・import・_ で始まる名前は拒否する。列名のバッククォート記法には対応しない。
"""
import ast
import operator

import numpy as np
from typing import Any, Callable


class SafeEvalError(ValueError):
    """式に許していない構文・名前・関数・属性がある。"""


DEFAULT_FUNCTIONS: dict[str, Any] = {
    'exp': np.exp, 'log': np.log, 'log10': np.log10, 'sqrt': np.sqrt,
    'sin': np.sin, 'cos': np.cos, 'tan': np.tan, 'abs': np.abs,
    'pi': np.pi, 'e': np.e,
}

# 列の計算でだけ許すメソッド。I/O、任意のコールバックを取るもの(apply など)、ダンダー名は入れない
ALLOWED_SERIES_METHODS = frozenset({
    'mean', 'std', 'var', 'min', 'max', 'median', 'sum', 'abs',
    'diff', 'cumsum', 'cumprod', 'cummax', 'cummin', 'pct_change',
    'shift', 'rolling', 'expanding', 'ewm', 'rank', 'round', 'clip',
    'quantile', 'skew', 'kurt', 'count', 'size',
})

_BINOPS: dict[type, Callable[..., Any]] = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}
# Series に素の not / and / or を使うと「真偽値が曖昧」になるので、pandas.eval と同じく ~ / & / | として扱う
_UNARYOPS: dict[type, Callable[..., Any]] = {ast.UAdd: operator.pos, ast.USub: operator.neg, ast.Not: operator.invert}
_BOOLOPS: dict[type, Callable[[Any, Any], Any]] = {ast.And: operator.and_, ast.Or: operator.or_}
_COMPAREOPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne,
    ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Gt: operator.gt, ast.GtE: operator.ge,
}


def _parse(formula: str) -> ast.expr:
    try:
        tree = ast.parse(formula, mode='eval')
    except SyntaxError as e:
        raise SafeEvalError(f"数式の構文が不正です: {e}") from e
    return tree.body


class _Evaluator:
    def __init__(self, variables: dict[str, Any], functions: dict[str, Any],
                 allowed_methods: frozenset[str] | None) -> None:
        self.variables = variables
        self.functions = functions
        # None なら属性アクセスを一切許さない(フィットの式)
        self.allowed_methods = allowed_methods

    def eval(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float, complex)):
                return node.value
            raise SafeEvalError(f"許可されていない定数です: {node.value!r}")

        if isinstance(node, ast.Name):
            if node.id in self.variables:
                return self.variables[node.id]
            if node.id in self.functions:
                return self.functions[node.id]
            raise SafeEvalError(f"未定義の変数/関数です: {node.id}")

        if isinstance(node, ast.BinOp):
            op = _BINOPS.get(type(node.op))
            if op is None:
                raise SafeEvalError(f"許可されていない演算子です: {type(node.op).__name__}")
            return op(self.eval(node.left), self.eval(node.right))

        if isinstance(node, ast.UnaryOp):
            op = _UNARYOPS.get(type(node.op))
            if op is None:
                raise SafeEvalError(f"許可されていない単項演算子です: {type(node.op).__name__}")
            return op(self.eval(node.operand))

        if isinstance(node, ast.Compare):
            left = self.eval(node.left)
            result = None
            for op_node, comparator in zip(node.ops, node.comparators):
                op = _COMPAREOPS.get(type(op_node))
                if op is None:
                    raise SafeEvalError(f"許可されていない比較演算子です: {type(op_node).__name__}")
                right = self.eval(comparator)
                partial = op(left, right)
                result = partial if result is None else (result & partial)
                left = right
            return result

        if isinstance(node, ast.BoolOp):
            op = _BOOLOPS.get(type(node.op))
            if op is None:
                raise SafeEvalError(f"許可されていない論理演算子です: {type(node.op).__name__}")
            values = [self.eval(v) for v in node.values]
            result = values[0]
            for v in values[1:]:
                result = op(result, v)
            return result

        if isinstance(node, ast.Attribute):
            if self.allowed_methods is None:
                raise SafeEvalError("この数式では属性アクセスは使用できません。")
            if node.attr.startswith('_') or node.attr not in self.allowed_methods:
                raise SafeEvalError(f"許可されていないメソッド/属性です: {node.attr}")
            return getattr(self.eval(node.value), node.attr)

        if isinstance(node, ast.Call):
            args = [self.eval(a) for a in node.args]
            # **expr の展開は kw.arg が None。拒否しないと関数呼び出しで TypeError が漏れる
            for kw in node.keywords:
                if kw.arg is None:
                    raise SafeEvalError("この形式の関数呼び出し(**による引数展開)は許可されていません。")
            kwargs = {str(kw.arg): self.eval(kw.value) for kw in node.keywords}
            if isinstance(node.func, ast.Name):
                name = node.func.id
                if name not in self.functions or not callable(self.functions[name]):
                    raise SafeEvalError(f"許可されていない関数です: {name}")
                return self.functions[name](*args, **kwargs)
            if isinstance(node.func, ast.Attribute):
                method = self.eval(node.func)
                if not callable(method):
                    raise SafeEvalError(f"'{node.func.attr}' は呼び出せません。")
                return method(*args, **kwargs)
            raise SafeEvalError("この形式の関数呼び出しは許可されていません。")

        raise SafeEvalError(f"許可されていない構文です: {type(node).__name__}")


def safe_eval_formula(formula: str, variables: dict[str, Any], functions: dict[str, Any] | None = None) -> Any:
    """フィットの式を評価する。属性アクセスとメソッド呼び出しは許さない。functions は DEFAULT_FUNCTIONS に足す。"""
    funcs = dict(DEFAULT_FUNCTIONS)
    if functions:
        funcs.update(functions)
    node = _parse(formula)
    return _Evaluator(variables, funcs, allowed_methods=None).eval(node)


def safe_eval_column_formula(df: Any, formula: str) -> Any:
    """列名を変数として列の計算式を評価する(ALLOWED_SERIES_METHODS のメソッドも使える)。"""
    variables = {str(col): df[col] for col in df.columns}
    node = _parse(formula)
    return _Evaluator(variables, dict(DEFAULT_FUNCTIONS), allowed_methods=ALLOWED_SERIES_METHODS).eval(node)
