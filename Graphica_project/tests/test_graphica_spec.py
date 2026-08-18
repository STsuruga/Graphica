# tests/test_graphica_spec.py
"""
graphica.spec (PyInstallerパッケージング定義) に対する回帰テスト。

graphica.specはPyInstallerが実行時に注入する特殊なビルトイン(Analysis/EXE/
BUNDLE/COLLECT/SPEC等)を前提としたファイルであり、通常のPythonモジュールと
してimport/execすることはできない(PyInstaller本体が無いテスト環境でも
壊れないよう、execはせずASTとして静的に解析するだけに留める)。

matplotlibのsavefig()はフォーマットに応じたバックエンドモジュールを
importlib.import_module()で実行時に動的読み込みするため、gui/canvas.py等に
直接のimport文が無くPyInstallerの静的解析では検出されない
(実機バグ: exe化して初めてSVGエクスポートがModuleNotFoundErrorになった)。
scipyもパッケージ構造上、同様の見落としが起きやすいことが実際に見つかった
(リリース前チェック)。このテストは、そうした「開発環境(python main.py)
では気づかず、exe/appビルドで初めて顕在化する」クラスの回帰を防ぐ。
"""
import ast
from pathlib import Path

SPEC_PATH = Path(__file__).parent.parent / "graphica.spec"


def _get_string_list_assignment(name):
    """graphica.spec中の `name = [...]` 代入を静的に解析し、文字列要素の
    リストを返す。"""
    tree = ast.parse(SPEC_PATH.read_text(encoding="utf-8"), filename=str(SPEC_PATH))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == name and isinstance(node.value, ast.List):
                return [
                    elt.value for elt in node.value.elts
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                ]
    raise AssertionError(f"'{name} = [...]' の代入がgraphica.spec内に見つからない")


def test_hiddenimports_includes_matplotlib_svg_and_pdf_backends():
    """
    実機バグ報告: exe化するとSVGエクスポートが
    'No module named matplotlib.backends.backend_svg' でクラッシュしていた。
    savefig(format='pdf')も同じ動的import経路のため併せて確認する。
    """
    hiddenimports = _get_string_list_assignment("hiddenimports")
    assert "matplotlib.backends.backend_svg" in hiddenimports
    assert "matplotlib.backends.backend_pdf" in hiddenimports


def test_hiddenimports_includes_scipy_submodules_used_outside_analysis_core():
    """
    リリース前チェックで発見: core/analysis.py(ベースライン補正ALS法・
    区間積分・Voigtフィットモデル)とgui/data_editor.py(列の要約統計量)が
    直接importしているscipyサブモジュールのうち、既存のhiddenimportsには
    scipy.interpolate/optimize/signalしか無く、scipy.sparse/
    scipy.sparse.linalg/scipy.integrate/scipy.special/scipy.statsが
    漏れていた(SVGバックエンドと同種の、exe化で初めて顕在化しうる見落とし)。
    """
    hiddenimports = _get_string_list_assignment("hiddenimports")
    for module in (
        "scipy.sparse", "scipy.sparse.linalg", "scipy.integrate",
        "scipy.special", "scipy.stats",
    ):
        assert module in hiddenimports, f"{module} がhiddenimportsに見つからない"


def test_hiddenimports_still_includes_previously_confirmed_scipy_submodules():
    """既存の(このテスト追加より前から列挙されていた)3つも回帰しないことを確認する。"""
    hiddenimports = _get_string_list_assignment("hiddenimports")
    for module in ("scipy.interpolate", "scipy.optimize", "scipy.signal"):
        assert module in hiddenimports


def test_datas_bundles_sample_data_directory_referenced_by_resource_path():
    """
    gui/main_window.pyのresource_path(os.path.join("sample_data",
    "cooling_curve_sample.csv"))が実際に参照するディレクトリが、
    datasリストで同梱対象になっていることを確認する。
    """
    text = SPEC_PATH.read_text(encoding="utf-8")
    assert '"sample_data"' in text
    sample_data_dir = SPEC_PATH.parent / "sample_data"
    assert (sample_data_dir / "cooling_curve_sample.csv").exists()


def test_datas_bundles_icons_directory_referenced_by_resource_path():
    """
    gui/main_window.py・gui/icon_utils.pyが参照するassets/icons配下の
    SVGファイル群が、datasリストで同梱対象になっていることを確認する。
    """
    text = SPEC_PATH.read_text(encoding="utf-8")
    assert '"icons"' in text
    icons_dir = SPEC_PATH.parent / "assets" / "icons"
    assert icons_dir.is_dir()
    assert len(list(icons_dir.glob("*.svg"))) > 0
