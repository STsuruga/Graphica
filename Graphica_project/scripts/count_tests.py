"""run_tests_chunked.sh 用: テストファイルごとの件数と重みを、import せずに見積もる。

1 行に「件数 TAB 重み TAB パス」を出す。pytest で収集すると全部を import するので 30 秒前後かかる。
パラメータ化は、引数がリスト・タプル・dict の直書きか、モジュールの変数のそれ(list(CASES) など)なら数える。
数えられないものは 1 件として数える(チャンクの釣り合いが少し崩れるだけ)。
"""
import ast
import re
import sys
import warnings

HEAVY_WEIGHT = 10
# ウィンドウを作るテストは 1 件約 0.5 秒で、ほかの数十倍かかる
HEAVY_PATTERN = re.compile(r"PlotterApp\(|_make_isolated_plotter_app|MainAppWindow\(|make_window")


def _length(node, names, depth=0):
    if depth > 5:
        return None
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return len(node.elts)
    if isinstance(node, ast.Dict):
        return len(node.keys)
    if isinstance(node, ast.Name) and node.id in names:
        return _length(names[node.id], names, depth + 1)
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name) and func.id in ("list", "tuple", "sorted") and node.args:
            return _length(node.args[0], names, depth + 1)
        if isinstance(func, ast.Name) and func.id == "range" and len(node.args) == 1 \
                and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, int):
            return node.args[0].value
        if isinstance(func, ast.Attribute) and func.attr in ("keys", "values", "items"):
            return _length(func.value, names, depth + 1)
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)) \
            and len(node.generators) == 1 and not node.generators[0].ifs:
        return _length(node.generators[0].iter, names, depth + 1)
    return None


def _cases(function, names):
    count = 1
    for decorator in function.decorator_list:
        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) \
                and decorator.func.attr == "parametrize" and len(decorator.args) >= 2:
            count *= _length(decorator.args[1], names) or 1
    return count


def count_tests(source):
    # テストのソースの不正なエスケープへの警告(実行時は pytest が出す)は、件数の見積もりには関係ない
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(source)
    names = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            names[node.targets[0].id] = node.value
    total = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            total += _cases(node, names)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and member.name.startswith("test"):
                    total += _cases(member, names)
    return total


def main(paths):
    for path in paths:
        with open(path, encoding="utf-8") as f:
            source = f.read()
        try:
            count = count_tests(source)
        except SyntaxError:
            # 収集でエラーとして出るよう、流す対象には残す
            count = 0
        # 特性テストはフィクスチャ経由でアプリを作る(ファイルの中には目印が無い)
        heavy = "characterization" in path.replace("\\", "/").split("/") or HEAVY_PATTERN.search(source)
        print(f"{count}\t{HEAVY_WEIGHT if heavy else 1}\t{path}")


if __name__ == "__main__":
    main(sys.argv[1:])
