"""
pip で入れた Graphica が起動できるかを確かめる(CI の install-check が、まっさらな仮想環境で使う)。

    python scripts/check_installed_app.py

ソースのフォルダではなく、インストール先の graphica を読み込んでいることも確かめる。
設定は一時フォルダに置くので、実行した人の設定は変えない。問題があれば終了コード 1。
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["GRAPHICA_CONFIRM_UNSAVED_CHANGES"] = "0"

SOURCE_ROOT = Path(__file__).resolve().parent.parent
# このスクリプトのフォルダ(scripts/)の親がソースの置き場所。そこを import の探索先から外す
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() not in (SOURCE_ROOT, SOURCE_ROOT / "scripts")]


def main():
    problems = []

    import graphica
    package_dir = Path(graphica.__file__).resolve().parent
    if SOURCE_ROOT in package_dir.parents:
        problems.append(f"ソースの graphica を読み込んでいます: {package_dir}")

    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    settings_path = os.path.join(tempfile.mkdtemp(), "graphica_check.ini")

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    import graphica.gui.main_app_window as main_app_window_module
    import graphica.gui.main_window as main_window_module
    main_window_module.QSettings = IsolatedQSettings
    main_app_window_module.QSettings = IsolatedQSettings
    # 初回の案内は、閉じるまで待つダイアログなので出さない
    IsolatedQSettings().setValue("has_shown_welcome", True)

    from graphica.core.version import __version__
    from graphica.gui.main_app_window import MainAppWindow
    from graphica.gui.main_window import resource_path

    for relative in ("Graphica.ico", os.path.join("assets", "icons"), "sample_data"):
        if not os.path.exists(resource_path(relative)):
            problems.append(f"同梱の {relative} が見つかりません")

    window = MainAppWindow()
    window.show()
    for _ in range(10):
        app.processEvents()
    tab = window.tab_widget.widget(0)
    if tab is None or not tab.canvas.all_axes:
        problems.append("最初のタブにグラフの軸がありません")
    if not tab.menuBar().actions():
        problems.append("メニューバーが空です")
    window.close()

    if problems:
        for problem in problems:
            print("NG:", problem)
        return 1
    print(f"OK: Graphica {__version__} を {package_dir} から起動できました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
