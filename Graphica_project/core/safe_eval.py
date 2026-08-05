# core/safe_eval.py
"""
ユーザー入力の数式文字列を eval()/exec() を一切使わずに評価するための
AST制限評価器 (C-008)。

使用箇所:
- core/analysis.py: カーブフィットのカスタム数式 ("a*exp(-b*x)+c" など)
- gui/data_editor.py, gui/mixins/dataset_mixin.py: データ列の計算式
  (旧 pandas.eval(formula, engine='python') の置き換え)

サポートする構文は「数値リテラル・変数参照・四則演算/べき乗/剰余・単項+-・
比較演算子・論理演算子(and/or/not、要素ごとの&/|/~として扱う)・
許可された関数呼び出し」。列演算 (safe_eval_column_formula) に限り、
加えて許可リストに載った pandas Series/Rolling 等のメソッド呼び出し
(例: A.mean(), A.rolling(5).mean()) も許可する。それ以外の構文
(属性アクセスの任意呼び出し、添字アクセス、ラムダ、内包表記、import文、
アンダースコアで始まる名前など) はすべて拒否する。

列名にバッククォート ( `列名` ) を使う pandas.eval() の記法には対応しない
(元コードの利用例・ダイアログのヘルプ文言はいずれも素の識別子のみを
想定しているため)。
"""
import ast
import operator

import numpy as np


class SafeEvalError(ValueError):
    """数式の構文/名前/関数/属性が許可されていない場合に送出する例外。"""


# --- 数式全般で使える数学関数/定数(カーブフィット・列計算で共通) ---
DEFAULT_FUNCTIONS = {
    'exp': np.exp, 'log': np.log, 'log10': np.log10, 'sqrt': np.sqrt,
    'sin': np.sin, 'cos': np.cos, 'tan': np.tan, 'abs': np.abs,
    'pi': np.pi, 'e': np.e,
}

# --- 列計算(DataFrame列演算)でのみ許可する Series/Rolling 等のメソッド名 ---
# I/O を伴うもの・任意コールバックを受け取るもの(apply/agg/transform等)・
# ダンダー名は含めない。
ALLOWED_SERIES_METHODS = frozenset({
    'mean', 'std', 'var', 'min', 'max', 'median', 'sum', 'abs',
    'diff', 'cumsum', 'cumprod', 'cummax', 'cummin', 'pct_change',
    'shift', 'rolling', 'expanding', 'ewm', 'rank', 'round', 'clip',
    'quantile', 'skew', 'kurt', 'count', 'size',
})

_BINOPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}
# ast.Not は Python の真偽判定(not)ではなく要素ごとの反転(~)にマップする。
# pandas Series に対して素の `not`/`and`/`or` を使うと「真偽値が曖昧」と
# いうエラーになるため、pandas.eval() 同様に and/or/not をそれぞれ
# &/|/~ の要素ごと演算として扱う(CalcHelpDialogのヘルプ文言もこの前提)。
_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg, ast.Not: operator.invert}
_BOOLOPS = {ast.And: operator.and_, ast.Or: operator.or_}
_COMPAREOPS = {
    ast.Eq: operator.eq, ast.NotEq: operator.ne,
    ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Gt: operator.gt, ast.GtE: operator.ge,
}


def _parse(formula):
    try:
        tree = ast.parse(formula, mode='eval')
    except SyntaxError as e:
        raise SafeEvalError(f"数式の構文が不正です: {e}") from e
    return tree.body


class _Evaluator:
    """許可された構文のみを再帰的に辿って評価するASTウォーカー。"""

    def __init__(self, variables, functions, allowed_methods):
        self.variables = variables
        self.functions = functions
        # None の場合は属性アクセス自体を一切許可しない(カーブフィット用)。
        self.allowed_methods = allowed_methods

    def eval(self, node):
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
            kwargs = {kw.arg: self.eval(kw.value) for kw in node.keywords}
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


def safe_eval_formula(formula, variables, functions=None):
    """
    数値/配列の数式を安全に評価する(core/analysis.py のカーブフィット用)。
    属性アクセス・メソッド呼び出しは一切許可しない。

    Args:
        formula (str): 数式文字列。
        variables (dict): 名前解決に使う変数(x・フィットパラメータ等)。
        functions (dict | None): DEFAULT_FUNCTIONS に追加/上書きする関数。
    """
    funcs = dict(DEFAULT_FUNCTIONS)
    if functions:
        funcs.update(functions)
    node = _parse(formula)
    return _Evaluator(variables, funcs, allowed_methods=None).eval(node)


def safe_eval_column_formula(df, formula):
    """
    DataFrame の列を参照する計算式を安全に評価する
    (gui/data_editor.py, gui/mixins/dataset_mixin.py の列計算用、
    pandas.eval(engine='python') の置き換え)。

    列名がそのまま変数名として使え、ALLOWED_SERIES_METHODS 内の
    Series/Rolling 等のメソッド呼び出し(mean(), rolling(5).mean() など)
    も許可する。

    Args:
        df (pandas.DataFrame): 列名を変数として公開する対象。
        formula (str): 計算式文字列。
    """
    variables = {str(col): df[col] for col in df.columns}
    node = _parse(formula)
    return _Evaluator(variables, dict(DEFAULT_FUNCTIONS), allowed_methods=ALLOWED_SERIES_METHODS).eval(node)
