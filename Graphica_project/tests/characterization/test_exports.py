"""書き出しを固定する: 画像(PNG・SVG・PDF)、クリップボード、印刷、一括書き出し、Python スクリプト、方法の文章、
HTML/PDF のレポート、LaTeX のキャプション。

画像とバイト列はピンした環境でだけハッシュを比べる。日時は SOURCE_DATE_EPOCH と時刻の固定で、SVG の要素 ID は
現れた順に振り直してから数える(matplotlib は ID の塩に uuid4 を使う)。
"""
import base64
import hashlib
import re
import time

import numpy as np
import pandas as pd
import pytest
from PySide6.QtWidgets import QApplication, QDialog

import recorder
from scenario import pump

ACCEPT = QDialog.DialogCode.Accepted


@pytest.fixture(autouse=True)
def _fixed_file_dates(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")  # 2026-01-01T00:00:00Z


def _project_tab(app_env, subplots=1):
    from graphica.core.dataset import Dataset

    tab = app_env.tab(size=(1300, 900))
    if subplots > 1:
        tab.subplot_rows_spinbox.setValue(subplots)
        pump()
    x = np.linspace(0.0, 10.0, 30)
    a = Dataset(df=pd.DataFrame({"x": x, "y": np.sin(x) + 2}), name="A", x_col_name="x", y_col_name="y")
    b = Dataset(df=pd.DataFrame({"x": x, "y": np.cos(x) + 2}), name="B", x_col_name="x", y_col_name="y",
                plot_type="Area", gradient_enabled=True, gradient_target="both", color="#2ca02c",
                subplot_target=subplots - 1)
    for ds in (a, b):
        tab._add_dataset(ds)
    settings = tab.project.all_plot_settings[0]
    settings.update({"title": "Export test", "x_label": "time (s)", "y_label": "signal"})
    tab._apply_settings_to_ui_controls(settings)
    tab._update_plot()
    pump()
    return tab


def _derive_with_provenance(tab, modal_log):
    """規格化 → 平滑化の 2 段の来歴を持つデータセットを作る。"""
    tree = tab.ui.dataset_list_widget
    tree.setCurrentItem(tab._get_dataset_tree_item(tab.project.datasets[0]))
    modal_log.accept_defaults()
    tab.processing.normalize()
    tree.setCurrentItem(tab._get_dataset_tree_item(tab.project.datasets[-1]))
    tab.processing.savgol_smooth()
    pump()
    return tab.project.datasets[-1]


def _png_rgba(data):
    import io

    import matplotlib.image as mpimg

    return (mpimg.imread(io.BytesIO(data), format="png") * 255).round().astype(np.uint8)


_SVG_ID = re.compile(r'id="([^"]+)"')


_EMBEDDED_PNG = re.compile(r"data:image/png;base64,([A-Za-z0-9+/=\s]+)")


def _pixels_digest(png_bytes):
    return hashlib.sha256(np.ascontiguousarray(_png_rgba(png_bytes)).tobytes()).hexdigest()[:16]


def normalize_svg(text):
    # 埋め込みの PNG は zlib の版で圧縮後のバイト列が変わるので、画素のハッシュに置き換える
    text = _EMBEDDED_PNG.sub(
        lambda m: "data:image/png;pixels," + _pixels_digest(base64.b64decode(re.sub(r"\s", "", m.group(1)))), text)
    ids = []
    for match in _SVG_ID.finditer(text):
        if match.group(1) not in ids:
            ids.append(match.group(1))
    for index, original in sorted(enumerate(ids), key=lambda item: -len(item[1])):
        text = re.sub(rf'(?<=["#(]){re.escape(original)}(?=[")])', f"id{index}", text)
    return text


_PDF_STREAM = re.compile(rb"(<<(?:(?!>>\s*stream).)*?>>)\s*stream\r?\n(.*?)\r?\nendstream", re.S)


def normalize_pdf(data):
    """圧縮した stream は展開した中身のハッシュにし、長さと相互参照表の位置は消す(どれも zlib の版で変わる)。"""
    import zlib

    def replace(match):
        header, body = match.group(1), match.group(2)
        if b"/FlateDecode" in header:
            try:
                body = zlib.decompress(body)
            except zlib.error:
                pass
        header = re.sub(rb"/Length\s+\d+(\s+0\s+R)?", b"/Length ?", header)
        return header + b" stream " + hashlib.sha256(body).hexdigest().encode() + b" endstream"

    data = _PDF_STREAM.sub(replace, data)
    data = re.sub(rb"xref.*?trailer", b"xref ? trailer", data, flags=re.S)
    data = re.sub(rb"startxref\s+\d+", b"startxref ?", data)
    # /Length を別のオブジェクトに置く書き方では、長さの数だけのオブジェクトができる
    return re.sub(rb"(\d+ 0 obj\s*)\d+(\s*endobj)", rb"\1?\2", data)


def _file_hashes(files):
    return {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}


def check_file_hashes(name, files):
    """バイト列のハッシュ。画素と同じく、ピンした環境でだけ比べる。"""
    if not recorder.pixel_environment_matches():
        return
    recorder.check(f"{name}.bytes", _file_hashes(files))


@pytest.mark.parametrize("fmt", ["png", "svg", "pdf"])
def test_export_plot(app_env, modal_log, normalizer, tmp_path, fmt):
    tab = _project_tab(app_env)
    modal_log.accept_defaults()
    modal_log.respond_to("getSaveFileName", (str(tmp_path / f"figure.{fmt}"), ""))
    tab._on_export_plot()
    pump()
    data = (tmp_path / f"figure.{fmt}").read_bytes()
    record = {"modals": modal_log.take(), "status": tab.statusBar().currentMessage(),
              "canvas_size_after": [round(v, 6) for v in tab.canvas.fig.get_size_inches()]}
    if fmt == "png":
        rgba = _png_rgba(data)
        record["image_shape"] = list(rgba.shape)
        recorder.check_pixels(f"exports/plot_{fmt}", {"file": rgba})
    elif fmt == "svg":
        check_file_hashes(f"exports/plot_{fmt}", {"file": normalize_svg(data.decode("utf-8")).encode("utf-8")})
    else:
        record["pdf_pages"] = data.count(b"/Type /Page\n") + data.count(b"/Type /Page ")
        check_file_hashes(f"exports/plot_{fmt}", {"file": normalize_pdf(data)})
    recorder.check(f"exports/plot_{fmt}", record, normalizer)


def test_copy_plot_to_clipboard_and_print(app_env, modal_log, normalizer):
    tab = _project_tab(app_env)
    modal_log.accept_defaults()
    tab._on_copy_plot_to_clipboard()
    image = QApplication.clipboard().image()
    # 変換した画像を変数に持っておかないと、読む前に解放される
    converted = image.convertToFormat(image.Format.Format_RGBA8888)
    rgba = np.frombuffer(converted.constBits(), dtype=np.uint8).reshape(
        converted.height(), converted.bytesPerLine() // 4, 4)[:, :converted.width()].copy()
    record = {"clipboard_modals": modal_log.take(), "status": tab.statusBar().currentMessage(),
              "clipboard_size": [image.width(), image.height()]}
    recorder.check_pixels("exports/clipboard", {"image": rgba})
    tab._on_print_plot()
    record["print_modals"] = modal_log.take()
    tab._on_show_cvd_simulation()
    record["cvd_modals"] = modal_log.take()
    recorder.check("exports/clipboard_print_cvd", record, normalizer)


def test_batch_export(app_env, modal_log, normalizer, tmp_path):
    from PySide6.QtCore import Qt

    tab = _project_tab(app_env, subplots=2)
    project_file = tmp_path / "other.graphica"
    tab._save_project_to_path(str(project_file))
    out_subplots = tmp_path / "subplots"
    out_files = tmp_path / "files"
    out_subplots.mkdir()
    out_files.mkdir()
    modal_log.accept_defaults()

    def subplots(dialog):
        dialog.output_dir_edit.setText(str(out_subplots))
        for i in range(dialog.subplot_list.count()):
            dialog.subplot_list.item(i).setCheckState(Qt.CheckState.Checked)
        return ACCEPT

    def project_files(dialog):
        dialog.mode_combo.setCurrentIndex(1)
        dialog.project_files_list.addItem(str(project_file))
        dialog.project_files_list.addItem(str(tmp_path / "missing.graphica"))
        dialog.output_dir_edit.setText(str(out_files))
        return ACCEPT

    def empty_dir(dialog):
        return ACCEPT

    results = {}
    images = {}
    for key, fill, folder in (("subplots", subplots, out_subplots), ("project_files", project_files, out_files),
                              ("no_output_dir", empty_dir, None)):
        modal_log.respond_to("exec", fill)
        tab._on_batch_export()
        deadline = time.monotonic() + 60
        while tab._batch_export_task_runner is not None:
            assert time.monotonic() < deadline, "一括書き出しが終わらなかった"
            pump(2)
            time.sleep(0.01)
        pump()
        written = sorted(p.name for p in folder.iterdir()) if folder else []
        results[key] = {"modals": modal_log.take(), "files": written}
        for name in written:
            images[f"{key}/{name}"] = _png_rgba((folder / name).read_bytes())
    recorder.check_pixels("exports/batch", images)
    recorder.check("exports/batch", results, normalizer)


def test_python_script(app_env, modal_log, normalizer, tmp_path):
    tab = _project_tab(app_env, subplots=2)
    modal_log.respond_to("getSaveFileName", (str(tmp_path / "plot"), ""))
    tab._on_export_python_script()
    recorder.check("exports/python_script", {
        "modals": modal_log.take(), "status": tab.statusBar().currentMessage(),
        "script": (tmp_path / "plot.py").read_text(encoding="utf-8"),
    }, normalizer)


def test_methods_text_and_reports(app_env, modal_log, normalizer, tmp_path):
    from graphica.core.methods_text import generate_methods_text

    tab = _project_tab(app_env)
    derived = _derive_with_provenance(tab, modal_log)
    modal_log.take()
    record = {"methods_text": generate_methods_text(derived, tab.project)}

    modal_log.respond_to("getSaveFileName", (str(tmp_path / "report.html"), ""))
    tab._on_generate_report()
    html = (tmp_path / "report.html").read_text(encoding="utf-8")
    images = [base64.b64decode(m) for m in re.findall(r"data:image/png;base64,([A-Za-z0-9+/=]+)", html)]
    record["html_modals"] = modal_log.take()
    record["html"] = re.sub(r"data:image/png;base64,[A-Za-z0-9+/=]+", "data:image/png;base64,<PNG>", html)
    recorder.check_pixels("exports/report_html", {f"image{i}": _png_rgba(data) for i, data in enumerate(images)})

    modal_log.respond_to("getSaveFileName", (str(tmp_path / "report.pdf"), ""))
    tab._on_generate_report()
    pdf = (tmp_path / "report.pdf").read_bytes()
    record["pdf_modals"] = modal_log.take()
    record["pdf_pages"] = pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ")
    record["status"] = tab.statusBar().currentMessage()
    # バイト列は比べない: 日本語の本文が Yu Gothic の部分フォントとして埋め込まれ、フォントの版(Windows 11 と
    # Windows Server で違う)で変わる。中身はページ数・HTML 版の本文・方法の文で押さえてある
    recorder.check("exports/methods_and_reports", record, normalizer)


def test_latex_caption(app_env, modal_log, normalizer):
    from graphica.core.caption_export import generate_latex_figure, sanitize_label

    tab = _project_tab(app_env)
    seen = {}

    def read_dialog(dialog):
        seen["initial"] = recorder.window_contents(dialog)
        dialog.image_name_edit.setText("figs/result.pdf")
        dialog.caption_edit.setText("温度 50% & 時間_1 の関係 #2")
        seen["edited"] = dialog.latex_preview.toPlainText()
        return QDialog.DialogCode.Rejected

    modal_log.respond_to("exec", read_dialog)
    tab._on_generate_caption()
    recorder.check("exports/latex_caption", {
        "modals": modal_log.take(), "dialog": seen,
        "labels": [sanitize_label(t) for t in ("Export test", "温度 & 時間", "", "a/b:c")],
        "figure": generate_latex_figure("fig.png", "説明 100% _x_", "fig:x"),
    }, normalizer)
