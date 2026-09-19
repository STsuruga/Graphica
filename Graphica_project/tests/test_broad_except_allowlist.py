"""`except Exception` を増やさないためのテスト。

広く例外を受けてよいのは、プラグインの隔離・スレッドやイベントの境界・利用者に
エラーを表示する箇所など、止めてはいけない場所だけ。どれもログに traceback を残す。
新しく書くときは、想定する例外の種類で受ける。どうしても必要なら、理由を
コメントに書いたうえで、この表の数を増やす。
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ALLOWED = {
    "graphica/core/analysis.py": 1,
    "graphica/core/diagnostics.py": 1,
    "graphica/core/excel_utils.py": 1,
    "graphica/core/plugin_api.py": 3,
    "graphica/gui/canvas.py": 4,
    "graphica/gui/crash_handler.py": 1,
    "graphica/gui/data_editor.py": 8,
    "graphica/gui/datasets/fitting.py": 1,
    "graphica/gui/datasets/peaks.py": 2,
    "graphica/gui/datasets/processing.py": 2,
    "graphica/gui/datasets/transfer.py": 4,
    "graphica/gui/dialogs/analysis.py": 2,
    "graphica/gui/dialogs/data_import.py": 6,
    "graphica/gui/export_preview_panel.py": 3,
    "graphica/gui/main_window.py": 9,
    "graphica/gui/minimap_widget.py": 2,
    "graphica/gui/mixins/dataset_mixin.py": 2,
    "graphica/gui/mixins/export_mixin.py": 11,
    "graphica/gui/mixins/help_mixin.py": 1,
    "graphica/gui/mixins/project_io_mixin.py": 4,
    "graphica/gui/mixins/settings_mixin.py": 1,
    "graphica/gui/plugin_context.py": 1,
    "graphica/gui/task_runner.py": 1,
    "graphica/gui/workers.py": 1,
}

_BROAD = {"Exception", "BaseException"}


def _is_broad(handler):
    if handler.type is None:
        return True
    names = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(isinstance(n, ast.Name) and n.id in _BROAD for n in names)


def _count_broad_handlers():
    counts = {}
    for package in ("graphica/core", "graphica/gui", "graphica/models"):
        for path in sorted((ROOT / package).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            n = sum(1 for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler) and _is_broad(node))
            if n:
                counts[path.relative_to(ROOT).as_posix()] = n
    return counts


def test_no_new_broad_except_handlers():
    grown = {
        path: (n, ALLOWED.get(path, 0))
        for path, n in _count_broad_handlers().items()
        if n > ALLOWED.get(path, 0)
    }
    assert not grown, f"except Exception が増えています (実際, 許可): {grown}"


def test_allowlist_is_not_stale():
    """減らしたら表も減らす。放っておくと、減った分だけ黙って増やせてしまう。"""
    counts = _count_broad_handlers()
    shrunk = {path: (counts.get(path, 0), n) for path, n in ALLOWED.items() if counts.get(path, 0) < n}
    assert not shrunk, f"許可リストを実際の数に合わせてください (実際, 許可): {shrunk}"
