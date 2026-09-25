"""記録器そのもののテスト。ここが緩いと、特性テストが挙動の変化を見逃す。"""
import json

import numpy as np
import pytest
from matplotlib.figure import Figure
from PySide6.QtWidgets import QDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

import recorder

pytestmark = pytest.mark.any_os


@pytest.fixture(autouse=True)
def _compare_mode(monkeypatch):
    # 基準の書き出し中(update_characterization.py)も、ここは比べる側の動きを確かめる
    monkeypatch.delenv(recorder.UPDATE_ENV, raising=False)


@pytest.fixture
def golden_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(recorder, "GOLDEN_DIR", tmp_path / "golden")
    monkeypatch.setattr(recorder, "IMAGE_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(recorder, "ARTIFACT_DIR", tmp_path / "artifacts")
    return tmp_path


def test_floats_are_rounded_and_special_values_spelled_out():
    assert recorder.to_jsonable([0.1 + 0.2, float("nan"), float("inf"), -0.0]) == [0.3, "NaN", "Infinity", 0.0]


def test_array_summary_ignores_last_digit_noise_but_not_real_changes():
    base = recorder.array_summary(np.array([1.0, 2.0, 3.0]))
    assert recorder.array_summary(np.array([1.0, 2.0, 3.0 + 1e-14])) == base
    assert recorder.array_summary(np.array([1.0, 2.0, 3.0001])) != base
    assert recorder.array_summary(np.array([1.0, 2.0])) != base


def test_normalizer_replaces_case_paths_and_version(tmp_path):
    from graphica.core.version import __version__

    norm = recorder.Normalizer()
    norm.add_path(tmp_path, "<CASE>")
    assert norm(f"{tmp_path}\\a.csv v{__version__}") == "<CASE>/a.csv v<VERSION>"


def test_normalized_paths_use_slashes_even_inside_repr(tmp_path):
    norm = recorder.Normalizer()
    norm.add_path(tmp_path, "<CASE>")
    inner = tmp_path / "sub" / "f.csv"
    assert norm(f"読み込み: {inner}") == "読み込み: <CASE>/sub/f.csv"
    assert norm(f"Errno 13: {str(inner)!r}") == "Errno 13: '<CASE>/sub/f.csv'"


def test_check_writes_in_update_mode_then_compares(golden_in_tmp, monkeypatch):
    monkeypatch.setenv(recorder.UPDATE_ENV, "1")
    recorder.check("group/case", {"a": 1, "b": [1.0, "x"]})
    monkeypatch.delenv(recorder.UPDATE_ENV)
    recorder.check("group/case", {"a": 1, "b": [1.0, "x"]})
    with pytest.raises(AssertionError) as info:
        recorder.check("group/case", {"a": 2, "b": [1.0], "c": True})
    message = str(info.value)
    assert "~ /a: 1 -> 2" in message
    assert "- /b[1]: 'x'" in message
    assert "+ /c: True" in message


def test_missing_golden_fails_instead_of_passing(golden_in_tmp):
    with pytest.raises(AssertionError, match="基準"):
        recorder.check("never_written", {"a": 1})


def test_pixel_mismatch_writes_actual_and_diff_images(golden_in_tmp, monkeypatch):
    monkeypatch.setattr(recorder, "pixel_environment_matches", lambda: True)
    image = np.zeros((4, 4, 4), dtype=np.uint8)
    image[..., 3] = 255
    monkeypatch.setenv(recorder.UPDATE_ENV, "1")
    recorder.check_pixels("pix", {"light": image})
    monkeypatch.delenv(recorder.UPDATE_ENV)
    recorder.check_pixels("pix", {"light": image.copy()})
    changed = image.copy()
    changed[0, 0, 0] = 255
    with pytest.raises(AssertionError, match="画素"):
        recorder.check_pixels("pix", {"light": changed})
    out = golden_in_tmp / "artifacts" / "pix"
    assert (out / "light.actual.png").exists()
    assert (out / "light.diff.png").exists()


def test_pixels_are_skipped_outside_the_pinned_environment(golden_in_tmp, monkeypatch):
    monkeypatch.setattr(recorder, "pixel_environment_matches", lambda: False)
    recorder.check_pixels("no_golden_needed", {"light": np.zeros((2, 2, 4), dtype=np.uint8)})


def test_widget_tree_records_text_state_and_child_order():
    root = QWidget()
    layout = QVBoxLayout(root)
    button = QPushButton("押す")
    button.setObjectName("go")
    button.setEnabled(False)
    label = QLabel("ラベル")
    label.setToolTip("説明")
    layout.addWidget(button)
    layout.addWidget(label)
    label.hide()
    tree = recorder.widget_tree(root)
    assert [c["class"] for c in tree["children"]] == ["QPushButton", "QLabel"]
    assert tree["children"][0] == {"class": "QPushButton", "name": "go", "text": "押す",
                                        "visible": True, "enabled": False}
    assert tree["children"][1]["visible"] is False
    assert tree["children"][1]["tooltip"] == "説明"


def test_axes_state_is_json_and_stable():
    def draw():
        figure = Figure(figsize=(3, 2), dpi=50)
        ax = figure.add_subplot()
        ax.plot([1, 2, 3], [1, 4, 9], color="red", label="a")
        ax.scatter([1, 2], [3, 4])
        ax.legend()
        figure.canvas.draw()
        return recorder.axes_state(ax), recorder.pixel_hash(recorder.rgba_of_figure(figure))

    first, second = draw(), draw()
    assert first == second
    state = first[0]
    json.dumps(state)
    assert state["lines"][0]["color"] == "#ff0000ff"
    assert state["legend"]["texts"] == ["a"]
    assert state["collections"][0]["offsets"]["shape"] == [2, 2]


def test_modal_log_records_and_answers(modal_log):
    assert QMessageBox.warning(None, "題", "本文") == QMessageBox.StandardButton.Ok
    modal_log.respond(QMessageBox.StandardButton.No)
    buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    assert QMessageBox.question(None, "問", "続ける?", buttons) == QMessageBox.StandardButton.No
    box = QMessageBox(QMessageBox.Icon.Critical, "箱", "中身")
    assert box.exec() == QDialog.DialogCode.Rejected.value
    assert modal_log.take() == [
        {"kind": "QMessageBox.warning", "title": "題", "text": "本文"},
        {"kind": "QMessageBox.question", "title": "問", "text": "続ける?", "buttons": ["Yes", "No"]},
        # macOS の Qt はメッセージボックスの題を捨てるので、Qt が返す値と比べる
        {"kind": "exec", "class": "QMessageBox", "title": box.windowTitle(), "text": "中身", "informative": "",
         "icon": "Critical", "buttons": []},
    ]


def test_modal_log_refuses_to_guess_a_yes_no_answer(modal_log):
    with pytest.raises(AssertionError, match="台本"):
        QMessageBox.question(None, "問", "続ける?")
