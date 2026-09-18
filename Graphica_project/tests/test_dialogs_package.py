# tests/test_dialogs_package.py
"""
`gui/dialogs/` パッケージの構造に対するテスト(改善ボード B-2)。

以前は `gui/dialogs.py` 1ファイル(5,560行・47ダイアログ)だった。機能が増える
たびにここへ足していく構造だったので、編集時の競合・検索性・レビューのしやすさに
効いてきていた。機能群ごとの6モジュールへ分割し、`__init__.py` で全部を
再エクスポートすることで**呼び出し側44箇所は1行も変えずに**済ませている。

このファイルが守るのは「分割したことで壊れやすくなった約束」の方:

1. **再エクスポートの網羅性**。新しいダイアログをサブモジュールに足したのに
   `__init__.py` へ足し忘れると、`from gui.dialogs import X` が
   ImportError になる。しかもそれは**そのダイアログを使う画面を開いた瞬間**まで
   分からない(このリポジトリの import はほとんどが関数内の遅延importなので、
   起動時には気づけない)。
2. **循環importを作らないこと**。分割前はクラス間の参照が4箇所しか無く、いずれも
   同じモジュールに収めてある。将来モジュールをまたぐ参照を足すと、`__init__` の
   import 順に依存して落ちるようになる。
3. **1ファイルが再び肥大化しないこと**。分割した意味が無くならないよう、
   上限を決めておく。
"""
import ast
import importlib
import pkgutil
from pathlib import Path

import pytest

import graphica.gui.dialogs as dialogs_package


PACKAGE_DIR = Path(dialogs_package.__file__).parent

# 分割時点での想定モジュール。増減させるときは、ここと __init__.py の表の
# 両方を更新すること(片方だけ直すと、どちらが正かが分からなくなる)。
EXPECTED_MODULES = {
    "analysis", "app", "appearance", "data_edit", "data_import", "export",
}

# 1モジュールの上限。分割前の 5,560行に戻さないための歯止めで、
# 現状の最大(analysis, 約1,700行)に余裕を持たせた値。
MAX_MODULE_LINES = 2500


def _submodule_names():
    return {m.name for m in pkgutil.iter_modules([str(PACKAGE_DIR)])}


def _iter_submodules():
    for name in sorted(_submodule_names()):
        yield name, importlib.import_module(f"graphica.gui.dialogs.{name}")


def _public_classes(module):
    """そのモジュールが**自分で定義した**公開クラス名。import してきたものは除く。"""
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    return {
        node.name for node in tree.body
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_")
    }


# --- パッケージの形 ---

def test_dialogs_is_a_package_not_a_single_module():
    assert PACKAGE_DIR.is_dir()
    assert (PACKAGE_DIR / "__init__.py").exists()
    assert not (PACKAGE_DIR.parent / "dialogs.py").exists(), \
        "分割前の gui/dialogs.py が残っている(パッケージと二重定義になる)"


def test_expected_modules_are_present():
    assert _submodule_names() == EXPECTED_MODULES


# --- 再エクスポートの網羅性 ---

def test_every_dialog_class_is_re_exported():
    """
    ★ 本命。サブモジュールに足したダイアログを `__init__.py` へ足し忘れると、
    `from gui.dialogs import X` が ImportError になる。このリポジトリの import は
    ほとんどが関数内の遅延importなので、起動時には気づけず「その画面を開いた
    瞬間に落ちる」という形で出る。
    """
    missing = []
    for name, module in _iter_submodules():
        for cls in _public_classes(module):
            if not hasattr(dialogs_package, cls):
                missing.append(f"{name}.{cls}")
    assert not missing, (
        "gui/dialogs/__init__.py の再エクスポートに足りていないクラス: "
        + ", ".join(sorted(missing))
    )


def test_all_lists_exactly_what_is_importable():
    assert dialogs_package.__all__, "__all__ が空"
    assert len(dialogs_package.__all__) == len(set(dialogs_package.__all__)), \
        "__all__ に重複がある"
    for name in dialogs_package.__all__:
        assert hasattr(dialogs_package, name), f"__all__ にあるが import されていない: {name}"


def test_all_covers_every_defined_dialog():
    defined = set()
    for _name, module in _iter_submodules():
        defined |= _public_classes(module)
    assert set(dialogs_package.__all__) == defined


def test_the_expected_number_of_dialogs_survived_the_split():
    """
    分割は**純粋な移動**なので、クラスが増減していたら何かを取りこぼしている。
    分割時点で47個。意図してダイアログを増やしたらこの数字も更新すること。
    """
    assert len(dialogs_package.__all__) == 47


# --- 呼び出し側との互換 ---

@pytest.mark.parametrize("class_name", [
    "ColumnPreviewDialog", "FitDialog", "LabelEditDialog", "PreferencesDialog",
    "ExportDialog", "NamedColorManagerDialog",
])
def test_callers_can_still_import_from_gui_dialogs(class_name):
    """
    呼び出し側44箇所はすべて `from gui.dialogs import X` の形。分割しても
    そのまま通ることが、この作業の前提条件だった。
    """
    module = importlib.import_module("graphica.gui.dialogs")
    assert isinstance(getattr(module, class_name), type)


def test_no_caller_had_to_switch_to_a_submodule_path():
    """
    本体のコードが `gui.dialogs.<サブモジュール>` を直接 import し始めていないこと。
    そうなると、ダイアログを別のモジュールへ移すたびに呼び出し側の修正が必要になり、
    再エクスポートで吸収している意味が無くなる。
    """
    project_root = PACKAGE_DIR.parent.parent.parent
    offenders = []
    for path in list((project_root / "graphica" / "gui").rglob("*.py")) + \
            list((project_root / "graphica" / "core").rglob("*.py")):
        if PACKAGE_DIR in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        for module_name in EXPECTED_MODULES:
            if f"gui.dialogs.{module_name}" in text:
                offenders.append(f"{path.relative_to(project_root)} -> {module_name}")
    assert not offenders, "サブモジュールを直接参照している: " + ", ".join(offenders)


# --- 分割の維持 ---

def test_no_module_grew_back_into_a_monolith():
    too_big = []
    for name, module in _iter_submodules():
        n_lines = len(Path(module.__file__).read_text(encoding="utf-8").split("\n"))
        if n_lines > MAX_MODULE_LINES:
            too_big.append(f"{name} ({n_lines}行)")
    assert not too_big, (
        f"{MAX_MODULE_LINES}行を超えたモジュール: " + ", ".join(too_big)
        + "。分割し直すか、新しい機能群を切ること"
    )


def test_submodules_do_not_import_each_other():
    """
    ★ 分割前のクラス間参照は4箇所だけで、いずれも同じモジュールに収めてある。
    モジュールをまたぐ参照を足すと、`__init__.py` の import 順に依存して
    落ちるようになる(しかも「たまたま今は通る」ことがあるので気づきにくい)。
    """
    offenders = []
    for name, module in _iter_submodules():
        text = Path(module.__file__).read_text(encoding="utf-8")
        for other in EXPECTED_MODULES - {name}:
            if f"gui.dialogs.{other}" in text:
                offenders.append(f"{name} -> {other}")
    assert not offenders, "サブモジュール間の import: " + ", ".join(offenders)


def test_the_package_is_shipped_by_pyproject():
    """
    ★ `pyproject.toml` の packages は明示列挙。新しいサブパッケージを足し忘れると、
    `pip install -e Graphica_project` した外部のプラグインリポジトリから
    gui.dialogs が見えなくなる(CLAUDE.md「A plugin repo tests against Graphica
    via pip install -e」参照)。
    """
    project_root = PACKAGE_DIR.parent.parent.parent
    text = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    assert '"graphica.gui.dialogs"' in text
