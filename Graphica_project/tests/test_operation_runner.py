"""データセットの処理の実行役(gui/datasets/operations/)の決まりごと。"""
import inspect

import pytest

import graphica.gui.notify as notify_module
from graphica.gui.datasets.operations.processing import PROCESSING_OPERATIONS
from graphica.gui.datasets.operations.runner import Operation, OperationState, run_operation
from graphica.gui.datasets.processing import ProcessingController


class _Host:
    parent_widget = None

    def __init__(self):
        self.added, self.status = [], []

    def current_dataset(self):
        return None

    def selected_datasets(self):
        return []

    def target_folder_for_new_dataset(self):
        return "folder"

    def add_dataset_with_undo(self, dataset, folder, description):
        self.added.append((dataset, folder, description))

    def show_status(self, text, timeout_ms):
        self.status.append((text, timeout_ms))


@pytest.fixture
def warnings(monkeypatch):
    shown = []
    monkeypatch.setattr(notify_module, "warning", lambda parent, title, text, *a: shown.append((title, text)))
    monkeypatch.setattr(notify_module, "information", lambda parent, title, text, *a: shown.append((title, text)))
    return shown


def _run(body):
    run_operation(Operation("題", body), _Host(), OperationState())


def test_a_value_error_from_the_calculation_becomes_a_warning_and_stops(warnings):
    reached = []

    def body(op):
        op.calculate(lambda: (_ for _ in ()).throw(ValueError("点が足りない")))
        reached.append(True)

    _run(body)
    assert warnings == [("題", "点が足りない")]
    assert reached == []


def test_other_errors_are_not_caught(warnings):
    with pytest.raises(TypeError):
        _run(lambda op: op.calculate(lambda: (_ for _ in ()).throw(TypeError("想定外"))))
    assert warnings == []


def _columns(x, y):
    return type("D", (), {"x_data": x, "y_data": y, "x_col_name": "名前", "y_col_name": "値"})()


def test_a_text_column_stops_with_a_warning_naming_it(warnings):
    reached = []

    def body(dataset):
        def run(op):
            op.valid_points(dataset)
            reached.append(True)
        return run

    _run(body(_columns(["a", "b"], [1.0, 2.0])))
    _run(body(_columns([1.0, 2.0], ["p", "q"])))
    assert warnings == [
        ("題", "X軸の列「名前」が数値ではないため、この処理はできません(文字の列はカテゴリ軸として表示だけできます)。"),
        ("題", "Y軸の列「値」が数値ではないため、この処理はできません。"),
    ]
    assert reached == []


def test_no_current_dataset_stops_silently(warnings):
    _run(lambda op: op.current_dataset())
    assert warnings == []


def test_selection_count_and_empty_name_messages(warnings):
    _run(lambda op: op.selected_datasets(exactly=2, message="2つ選んで"))
    _run(lambda op: op.require_output_name(""))
    assert warnings == [("題", "2つ選んで"), ("入力エラー", "出力データセット名が空です。")]


def test_add_and_report_adds_undoably_under_the_operation_title():
    host = _Host()
    dataset = type("D", (), {"name": "結果"})()
    run_operation(Operation("題", lambda op: op.add_and_report(dataset)), host, OperationState())
    assert host.added == [(dataset, "folder", "題")]
    assert host.status == [("「結果」を追加しました", 3000)]


def test_every_menu_entry_runs_an_operation_in_the_table():
    controller = ProcessingController(_Host())
    called = []
    controller._run = called.append
    entries = [name for name, member in inspect.getmembers(ProcessingController, inspect.isfunction)
               if not name.startswith("_")]
    for name in entries:
        getattr(controller, name)()
    assert sorted(called) == sorted(PROCESSING_OPERATIONS)
    assert all(op.title for op in PROCESSING_OPERATIONS.values())


@pytest.mark.parametrize("module_name, controller_name, table_name", [
    ("peaks", "PeakController", "PEAK_OPERATIONS"),
    ("transfer", "TransferController", "TRANSFER_OPERATIONS"),
    ("fitting", "FittingController", "FITTING_OPERATIONS"),
])
def test_the_other_controllers_only_run_their_tables(module_name, controller_name, table_name, monkeypatch):
    import importlib

    controller_module = importlib.import_module(f"graphica.gui.datasets.{module_name}")
    table = getattr(importlib.import_module(f"graphica.gui.datasets.operations.{module_name}"), table_name)
    ran = []
    monkeypatch.setattr(controller_module, "run_operation", lambda operation, host, state: ran.append(operation))
    controller = getattr(controller_module, controller_name)(_Host())
    for name, _member in inspect.getmembers(type(controller), inspect.isfunction):
        if name.startswith("_") or name == "shutdown":
            continue
        calls = {"copy_or_move_to_tab": [(False,), (True,)], "burn_fit_result_annotation": [(None, None)]}
        for args in calls.get(name, [()]):
            getattr(controller, name)(*args)
    assert set(table.values()) <= set(ran)
    assert all(isinstance(op, Operation) and op.title for op in ran)
