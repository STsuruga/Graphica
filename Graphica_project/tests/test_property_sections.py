# tests/test_property_sections.py
"""
「データセットのプロパティ」パネルのサブセクション化に対するテスト(改善ボード C-1)。

従来は Designer 生成分+実行時追加の **39行が1本の QFormLayout(formLayout_4)**に
縦積みされており、プロット種別や2Dマップのトグルひとつでパネル高さが
763px〜1134px まで伸縮していた(実測)。これを7つの折りたたみ可能な
サブセクションに分割したのが C-1 で、このファイルはその構造を固定する。

固めるのは主に3点:

1. **行が1つも迷子にならないこと**。分割の実体は「39回の addRow の宛先を
   変える」作業なので、宛先の書き間違いは「そのウィジェットがどのレイアウトにも
   属さず、グループボックスの左上に重なって描画される」という、テストが無いと
   気づきにくい壊れ方をする。
2. **条件付き表示との噛み合わせ**。中身が全部隠れたセクションは見出しごと
   隠す(でないと折りたたみで減らしたぶんを見出しが食い返す)。
3. **開閉状態の永続化**。既定は全展開で、ユーザーが閉じたものだけを
   QSettings に記録する(キーが無い=全展開、なので新セクションを足しても安全)。

あわせて、D-2 でフラグしたまま未修正だった「プラグインが長い plot_type 名を
登録するとプロパティドックが横にはみ出す」問題の回帰テストもここに置く
(直し方がサブセクション化と同じ「QFormLayout の列幅の波及」の話なので)。
"""
import json

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import pytest
from PySide6.QtCore import Qt, QSettings
from PySide6.QtWidgets import QApplication, QFormLayout, QToolButton

import graphica.gui.app_settings as app_settings_module
import graphica.core.plugin_api as plugin_api_module
from graphica.core.dataset import Dataset, COLOR_BY_COLUMN_PLOT_TYPE
from graphica.core.plugin_api import GraphicaPluginAPI
from graphica.gui.app_settings import DATASET_PROPERTY_COLLAPSED_SECTIONS_KEY
from graphica.gui.main_window import DATASET_PROPERTY_SECTIONS, PLOT_TYPE_COMBO_MIN_CHARS, PlotterApp


def _make_isolated_plotter_app(tmp_path, monkeypatch, settings_name="test_settings.ini"):
    settings_path = str(tmp_path / settings_name)

    class IsolatedQSettings(QSettings):
        def __init__(self, *args, **kwargs):
            super().__init__(settings_path, QSettings.Format.IniFormat)

    monkeypatch.setattr(app_settings_module, "QSettings", IsolatedQSettings)
    window = PlotterApp(run_startup_checks=False, tab_id=2)
    window.resize(1100, 600)
    window.show()
    app = QApplication.instance()
    for _ in range(5):
        app.processEvents()
    return window


@pytest.fixture
def window(tmp_path, monkeypatch):
    w = _make_isolated_plotter_app(tmp_path, monkeypatch)
    yield w
    w.close()


def _pump():
    app = QApplication.instance()
    for _ in range(4):
        app.processEvents()


def _section_widgets(window, key):
    """セクション内の全ウィジェットを、行順・(ラベル→フィールド)の順で返す。"""
    form = window._prop_form(key)
    out = []
    for row in range(form.rowCount()):
        for role in (QFormLayout.ItemRole.LabelRole,
                     QFormLayout.ItemRole.FieldRole,
                     QFormLayout.ItemRole.SpanningRole):
            item = form.itemAt(row, role)
            if item is not None and item.widget() is not None \
                    and item.widget() not in out:
                out.append(item.widget())
    return out


def _visible_row_labels(window, key):
    """セクション内の「今表示されている」行を、ラベル文字列で返す。"""
    form = window._prop_form(key)
    labels = []
    for row in range(form.rowCount()):
        text, shown = None, False
        for role in (QFormLayout.ItemRole.LabelRole,
                     QFormLayout.ItemRole.FieldRole,
                     QFormLayout.ItemRole.SpanningRole):
            item = form.itemAt(row, role)
            if item is None or item.widget() is None:
                continue
            widget = item.widget()
            if not widget.isHidden():
                shown = True
            if text is None and getattr(widget, "text", None) and widget.text():
                text = widget.text()
        if shown:
            labels.append(text)
    return labels


def _make_dataset(window, name="ds"):
    df = pd.DataFrame({'x': np.arange(10.0), 'y': np.arange(10.0), 'z': np.arange(10.0)})
    dataset = Dataset(df=df, name=name, x_col_name='x', y_col_name='y')
    window._add_dataset(dataset)
    _pump()
    return dataset


# --- 構造 ---

def test_seven_sections_exist_in_the_declared_order(window):
    keys = [key for key, _title in DATASET_PROPERTY_SECTIONS]
    assert keys == ['data', 'style', 'gradient', 'waterfall', 'map', 'extra', 'place']
    assert set(window._prop_sections) == set(keys)


def test_the_original_form_layout_is_left_empty(window):
    """
    Designer 生成の formLayout_4 は ui_main_window.py 側の構造なので取り除かずに
    残すが、中身は全てサブセクションへ移設され0行になっていること。
    1行でも残っていたら、それは移設し忘れた行がドックの先頭に居座っている。
    """
    assert window.ui.formLayout_4.rowCount() == 0


def test_every_property_row_lives_in_exactly_one_section(window):
    """39行(+ v1.4.2 で足したデータ点ラベルの上限超過の説明1行)が過不足なく7セクションに分配されていること。"""
    total = sum(window._prop_form(key).rowCount() for key, _ in DATASET_PROPERTY_SECTIONS)
    assert total == 40


def test_no_property_widget_is_orphaned_from_every_layout(window):
    """
    ★ この分割でいちばん起きやすい事故の直接のテスト。takeRow() で
    formLayout_4 から外したまま、どのセクションにも addRow し忘れると、
    ウィジェットは削除もされず警告も出ず、groupbox の左上に重なって描く。
    Designer 生成の8行(特に「平滑化」チェックボックスは意図的に移設を
    保留して後から足しているので危ない)が全て回収されていることを見る。
    """
    placed = set()
    for key, _title in DATASET_PROPERTY_SECTIONS:
        placed.update(id(w) for w in _section_widgets(window, key))

    designer_widgets = [
        window.ui.legend_name_label, window.ui.legend_name_edit,
        window.ui.plot_type_label, window.ui.plot_type_combo,
        window.ui.color_label, window.color_picker_widget,
        window.ui.linestyle_label, window.ui.linestyle_combo,
        window.ui.linewidth_label, window.ui.linewidth_spinbox,
        window.ui.marker_label, window.ui.marker_combo,
        window.ui.makersize_label, window.ui.markersize_spinbox,
        window.ui.smoothing_checkbox,
    ]
    missing = [w.objectName() or type(w).__name__
               for w in designer_widgets if id(w) not in placed]
    assert not missing, f"どのセクションにも属していないウィジェット: {missing}"


@pytest.mark.parametrize("section_key, widget_attr", [
    ('data', 'x_col_combo'),
    ('data', 'y_col_combo'),
    ('data', 'x_err_col_combo'),
    ('data', 'y_err_col_combo'),
    ('data', 'nan_policy_combo'),
    ('style', 'alpha_spinbox'),
    ('style', 'smoothing_method_combo'),
    ('gradient', 'gradient_checkbox'),
    ('gradient', 'gradient_color2_picker'),
    ('gradient', 'gradient_target_combo'),
    ('waterfall', 'waterfall_checkbox'),
    ('waterfall', 'waterfall_offset_x_spinbox'),
    ('waterfall', 'waterfall_depth_ratio_spinbox'),
    ('map', 'data_2d_checkbox'),
    ('map', 'z_col_combo'),
    ('map', 'colormap_combo'),
    ('map', 'vmax_spinbox'),
    ('extra', 'point_labels_checkbox'),
    ('extra', 'point_labels_limit_note'),
    ('extra', 'point_label_col_combo'),
    ('extra', 'error_display_combo'),
    ('place', 'use_secondary_y_checkbox'),
    ('place', 'subplot_target_combo'),
    ('place', 'fit_info_textedit'),
])
def test_widget_is_in_its_declared_section(window, section_key, widget_attr):
    widget = getattr(window, widget_attr)
    assert widget in _section_widgets(window, section_key)


def test_data_section_row_order(window):
    """
    X→Y、X誤差→Y誤差 の順であること。旧実装は insertRow(1, Y) → insertRow(1, X)
    という「2回呼ぶと順序が入れ替わる」書き方で目的の順序を作っていたので、
    addRow への機械的な置換ではここが逆転する。
    """
    assert _visible_row_labels(window, 'data') == [
        "X軸の列", "Y軸の列", "X誤差列", "Y誤差列", "欠損値の扱い",
    ]


def test_smoothing_checkbox_sits_directly_above_its_method_combo(window):
    """
    「平滑化」と「平滑化の手法」は必ず一緒に出入りする対なので隣接させる。
    Designer 行をそのまま移設すると間に「透明度」が挟まる。
    """
    widgets = _section_widgets(window, 'style')
    i_check = widgets.index(window.ui.smoothing_checkbox)
    i_label = widgets.index(window.smoothing_method_label)
    assert i_label == i_check + 1


def test_fit_info_is_the_last_row_of_its_section(window):
    """
    フィットが無いときは隠れる100px高の欄なので、セクションの先頭にあると
    フィットするたびに下の項目が押し下げられる。末尾に置く。
    """
    widgets = _section_widgets(window, 'place')
    assert widgets[-1] is window.fit_info_textedit


# --- 見出しのトグル ---

def test_subsection_toggles_use_their_own_object_name(window):
    """
    トップレベルの2セクション(項目102)と同じ objectName を使うと、
    theme.py のスタイルが同じ強さで当たって階層が読めなくなるうえ、
    「トグルボタンはちょうど2つ」を前提にした既存テストも壊れる。
    """
    groupbox = window.ui.properties_groupbox
    subs = [b for b in groupbox.findChildren(QToolButton)
            if b.objectName() == "property_subsection_toggle"]
    assert len(subs) == len(DATASET_PROPERTY_SECTIONS)

    dock = window.ui.control_dock_widget
    tops = [b for b in dock.findChildren(QToolButton)
            if b.objectName() == "collapsible_section_toggle"]
    assert len(tops) == 2


def test_all_sections_are_expanded_by_default(window):
    """ユーザー決定: 既定は全展開(初回起動の見え方は従来と実質同じ)。"""
    for key, _title in DATASET_PROPERTY_SECTIONS:
        entry = window._prop_sections[key]
        assert entry['toggle'].isChecked() is True
        assert entry['body'].isHidden() is False


def test_collapsing_a_section_hides_its_body_but_keeps_the_header(window):
    entry = window._prop_sections['map']
    entry['toggle'].setChecked(False)
    _pump()

    assert entry['body'].isHidden() is True
    assert entry['toggle'].isHidden() is False
    assert entry['section'].isHidden() is False


def test_sections_can_be_toggled_before_any_dataset_exists(window):
    """
    ★ 実機フィードバックの回帰テスト:「データ追加するまで動かせない」。
    Designer は properties_groupbox 自体を setEnabled(False) にしており、
    Qt は無効な親の下の子を個別に有効化できないため、セクションをその中に
    入れた時点で「データセットを1つも追加していないと開閉すらできない」
    状態になっていた。開閉はパネルの見せ方の操作であって、選択中の
    データセットを編集する操作ではない。
    """
    assert window._get_current_dataset() is None

    for key, _title in DATASET_PROPERTY_SECTIONS:
        entry = window._prop_sections[key]
        assert entry['toggle'].isEnabled() is True, f"{key} の見出しが押せない"

    entry = window._prop_sections['map']
    entry['toggle'].setChecked(False)
    _pump()
    assert entry['body'].isHidden() is True


def test_property_fields_are_disabled_until_a_dataset_is_selected(window):
    """見出しは常に押せる一方で、入力欄そのものは従来どおり無効であること。"""
    for key, _title in DATASET_PROPERTY_SECTIONS:
        assert window._prop_sections[key]['body'].isEnabled() is False
    assert window.ui.plot_type_combo.isEnabled() is False

    _make_dataset(window)

    for key, _title in DATASET_PROPERTY_SECTIONS:
        assert window._prop_sections[key]['body'].isEnabled() is True
    assert window.ui.plot_type_combo.isEnabled() is True


def test_no_dead_gap_above_the_first_subsection(window):
    """
    ★ 実機フィードバック(画像提示)の回帰テスト: 「データセットのプロパティ」の
    見出しと最初のサブセクション「データ列」の間に、24px+9px の使われない
    隙間が空いていた。24pxは theme.py の QDockWidget QGroupBox が
    「自身のタイトルを置く場所」として確保する margin-top/padding-top だが、
    このグループボックスはタイトルを空にして見出しを外へ出しているので
    丸ごと無駄になっていた。9px は gridLayout_4 の既定余白。
    """
    container = window._dataset_property_sections_container
    top_offset = container.mapTo(window.ui.properties_groupbox, container.rect().topLeft()).y()
    assert top_offset <= 4, f"見出し直下に {top_offset}px の隙間が残っている"


def test_collapsible_group_boxes_are_flagged_for_the_stylesheet(window):
    """theme.py の QGroupBox[collapsibleBody="true"] が効く前提の目印。"""
    assert window.ui.properties_groupbox.property("collapsibleBody") is True


def test_collapsing_shortens_the_panel(window):
    _make_dataset(window)
    before = window.ui.properties_groupbox.sizeHint().height()

    for key in ('gradient', 'waterfall', 'map'):
        window._prop_sections[key]['toggle'].setChecked(False)
    _pump()

    assert window.ui.properties_groupbox.sizeHint().height() < before


# --- 開閉状態の永続化 ---

def test_collapsed_sections_are_written_to_qsettings(window):
    window._prop_sections['waterfall']['toggle'].setChecked(False)
    window._prop_sections['map']['toggle'].setChecked(False)
    _pump()

    raw = window.settings.value(DATASET_PROPERTY_COLLAPSED_SECTIONS_KEY, "[]")
    assert sorted(json.loads(raw)) == ['map', 'waterfall']


def test_reopening_a_section_removes_it_from_qsettings(window):
    toggle = window._prop_sections['waterfall']['toggle']
    toggle.setChecked(False)
    toggle.setChecked(True)
    _pump()

    raw = window.settings.value(DATASET_PROPERTY_COLLAPSED_SECTIONS_KEY, "[]")
    assert json.loads(raw) == []


def test_collapsed_state_survives_a_new_window(tmp_path, monkeypatch):
    """★ ユーザー決定の肝。一度閉じたセクションは次の起動でも閉じたまま。"""
    first = _make_isolated_plotter_app(tmp_path, monkeypatch, "shared.ini")
    first._prop_sections['map']['toggle'].setChecked(False)
    _pump()
    first.close()

    second = _make_isolated_plotter_app(tmp_path, monkeypatch, "shared.ini")
    try:
        assert second._prop_sections['map']['toggle'].isChecked() is False
        assert second._prop_sections['data']['toggle'].isChecked() is True
    finally:
        second.close()


@pytest.mark.parametrize("stored", ["", "not json", "{}", '["nope"]', '["map", 7]'])
def test_broken_or_unknown_stored_values_fall_back_to_all_expanded(
        tmp_path, monkeypatch, stored):
    """
    設定ファイルが壊れていたり、将来セクションキーを改名したりしても、
    「全部展開」に倒れるだけでクラッシュしないこと。
    """
    settings_path = str(tmp_path / "broken.ini")
    seed = QSettings(settings_path, QSettings.Format.IniFormat)
    seed.setValue(DATASET_PROPERTY_COLLAPSED_SECTIONS_KEY, stored)
    seed.sync()

    window = _make_isolated_plotter_app(tmp_path, monkeypatch, "broken.ini")
    try:
        expanded = [key for key, _ in DATASET_PROPERTY_SECTIONS
                    if window._prop_sections[key]['toggle'].isChecked()]
        if stored == '["map", 7]':
            # 既知のキーだけ拾い、数値は無視する
            assert 'map' not in expanded
        else:
            assert len(expanded) == len(DATASET_PROPERTY_SECTIONS)
    finally:
        window.close()


# --- 条件付き表示との噛み合わせ ---

def test_waterfall_section_is_hidden_entirely_for_a_2d_grid_dataset(window):
    """
    A-5 で「2Dマップではウォーターフォールの9行を隠す」と決めたので、
    このセクションは中身が全滅する。見出しだけ残ると、折りたたみで
    減らしたぶんを見出しが食い返す(C-2 の「空のサブメニューは出さない」と同じ)。
    """
    dataset = _make_dataset(window)
    assert window._prop_sections['waterfall']['section'].isHidden() is False

    dataset.data_kind = '2d_grid'
    dataset.z_col_name = 'z'
    window.property_panel.update_ui_state()
    _pump()

    assert window._prop_sections['waterfall']['section'].isHidden() is True
    assert window._prop_sections['map']['section'].isHidden() is False


def test_waterfall_section_comes_back_when_the_dataset_is_1d_again(window):
    dataset = _make_dataset(window)
    dataset.data_kind = '2d_grid'
    window.property_panel.update_ui_state()
    _pump()
    assert window._prop_sections['waterfall']['section'].isHidden() is True

    dataset.data_kind = '1d'
    window.property_panel.update_ui_state()
    _pump()
    assert window._prop_sections['waterfall']['section'].isHidden() is False


def test_gradient_section_is_hidden_for_plot_types_that_cannot_use_it(window):
    """グラデーションは Line / Line+Scatter / Area でのみ意味を持つ。"""
    dataset = _make_dataset(window)
    dataset.plot_type = 'Line'
    window.property_panel.update_ui_state()
    _pump()
    assert window._prop_sections['gradient']['section'].isHidden() is False

    dataset.plot_type = 'Scatter'
    window.property_panel.update_ui_state()
    _pump()
    assert window._prop_sections['gradient']['section'].isHidden() is True


def test_map_section_shows_the_shared_rows_for_a_z_color_scatter(window):
    """
    D-2 の 'Z-Color Scatter' は2Dグリッドではないが、Z列・カラーマップ・値域を
    共用する。セクションは出るが、グリッド固有の3行は出ないこと。
    """
    dataset = _make_dataset(window)
    dataset.plot_type = COLOR_BY_COLUMN_PLOT_TYPE
    dataset.z_col_name = 'z'
    window.property_panel.update_ui_state()
    _pump()

    assert window._prop_sections['map']['section'].isHidden() is False
    shown = _visible_row_labels(window, 'map')
    assert "Z軸の列" in shown
    assert "カラーマップ" in shown
    assert "表示方式" not in shown
    assert "等高線レベル数" not in shown


def test_switching_plot_type_no_longer_moves_rows_across_sections(window):
    """
    C-1 の目的そのもの: 種別を切り替えても「データ列」「基本スタイル」の
    中身と並びは一切動かない(伸縮するのは専用セクションの中だけ)。
    """
    dataset = _make_dataset(window)
    before_data = _visible_row_labels(window, 'data')
    before_style = _visible_row_labels(window, 'style')

    dataset.data_kind = '2d_grid'
    dataset.z_col_name = 'z'
    window.property_panel.update_ui_state()
    _pump()

    assert _visible_row_labels(window, 'data') == before_data
    assert _visible_row_labels(window, 'style') == before_style


# --- プラグイン製 plot_type の横はみ出し(D-2 でフラグ、C-1 で対応) ---

def test_plot_type_combo_width_is_capped(window):
    from PySide6.QtWidgets import QComboBox
    assert window.ui.plot_type_combo.sizeAdjustPolicy() == \
        QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    assert window.ui.plot_type_combo.minimumContentsLength() == PLOT_TYPE_COMBO_MIN_CHARS


def test_a_long_plugin_plot_type_name_does_not_widen_the_dock(tmp_path, monkeypatch):
    """
    ★ D-2 で「未修正の潜在問題」としてフラグしていた回帰の本体。
    当時は組み込み種別を15文字に縮めて回避したが、プラグインが登録する名前は
    任意長なので、根本対処が無いと同じ横スクロールバーが出る。
    """
    api = GraphicaPluginAPI()
    api.register_plot_type(
        "Extremely Long Plugin Plot Type Name That Would Overflow",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(plugin_api_module, "_singleton_api", api)

    window = _make_isolated_plotter_app(tmp_path, monkeypatch)
    try:
        assert window.ui.plot_type_combo.findText(
            "Extremely Long Plugin Plot Type Name That Would Overflow") != -1

        scroll_area = window.ui.control_dock_widget.widget()
        assert scroll_area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        assert scroll_area.horizontalScrollBar().maximum() == 0
        assert scroll_area.widget().minimumSizeHint().width() <= scroll_area.viewport().width()
    finally:
        window.close()


# --- 見出しと項目の見分け(実機フィードバック) ---

def _left_padding(qss, selector):
    """生成済みQSSから、あるセレクタの padding の左値(px)を読む。"""
    import re
    block = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", qss)
    assert block, f"{selector} の規則が見つからない"
    decl = re.search(r"padding:\s*([^;]+);", block.group(1))
    assert decl, f"{selector} に padding 指定が無い"
    values = decl.group(1).split()
    # CSSショートハンド: 1値=全辺, 2値=縦/横, 3値=上/横/下, 4値=上右下左
    left = {1: 0, 2: 1, 3: 1, 4: 3}[len(values)]
    return int(values[left].replace("px", ""))


def _rendered_height(widget):
    """そのウィジェットが実際に描かれる文字の高さ(px)。

    ★ QSSに書いた数値ではなく、**描画に使われるフォントの実寸**で比べること。
    QSSの指定はptで、フォームのラベルはOS既定(Windows 9pt / macOS 13pt前後)
    なので、単位も基準も違う値を突き合わせても意味がない。
    """
    from PySide6.QtGui import QFontMetrics
    return QFontMetrics(widget.font()).height()


def _top_level_toggle(window):
    for button in window.ui.control_dock_widget.findChildren(QToolButton):
        if button.objectName() == "collapsible_section_toggle":
            return button
    raise AssertionError("トップレベルのアコーディオン見出しが見つからない")


def test_indent_forms_a_ladder_from_parent_to_child_to_content(window):
    """
    ★ 実機フィードバックの回帰テスト:「インデントが逆転してるのなんかやだ」。
    親の見出しは padding-left:4px で描かれるのに子は0で、子のほうが4px左に
    出ていた。親 < 子 < 中身 の順に深くなること。
    """
    from graphica.gui import theme
    qss = theme.build_qss(theme.LIGHT_TOKENS)

    parent = _left_padding(qss, "QToolButton#collapsible_section_toggle")
    child = _left_padding(qss, "QToolButton#property_subsection_toggle")
    content = window._prop_form('data').contentsMargins().left()

    assert parent < child < content, f"親={parent} 子={child} 中身={content}"


def test_headings_are_larger_than_the_fields_they_contain(window):
    """
    ★ 実機フィードバックの回帰テスト:「見出し文字サイズが中の項目より
    小さい気がする」。このアプリはQSSでフォントサイズを指定していないため、
    フォームのラベルはOS既定で描かれる。

    ★★ その既定は **Windowsで9pt、macOSで13pt前後** と差が大きい。最初の修正では
    見出しをpx固定にしたため、Windowsでは直ったのにmacOSでは
    「見出し13px < 項目15px」と逆転したままになり、macOSのCIで検出された。
    現在は `theme.heading_point_sizes()` がアプリ既定フォントからの相対で
    決めている。ここでは**実際に描かれる文字の高さ**同士を比べる
    (QSSに書いた数値と突き合わせても、単位も基準も違うので意味がない)。
    """
    from PySide6.QtWidgets import QFormLayout

    parent = _rendered_height(_top_level_toggle(window))
    child = _rendered_height(window._prop_sections['data']['toggle'])
    label_widget = window._prop_form('data').itemAt(0, QFormLayout.ItemRole.LabelRole).widget()
    field = _rendered_height(label_widget)

    assert parent > child > field,         f"親見出し={parent} サブ見出し={child} 項目ラベル={field}"


def test_heading_sizes_follow_the_application_font(window):
    """
    ★ px 固定に戻さないための歯止め。OS既定フォントが変わっても
    「親 > 子 > 本文」の順序が保たれるよう、相対で決めること。
    """
    from graphica.gui import theme

    heading_pt, subheading_pt = theme.heading_point_sizes()
    base_pt = QApplication.instance().font().pointSizeF()

    assert heading_pt > subheading_pt > base_pt,         f"親={heading_pt} 子={subheading_pt} 既定={base_pt}"

    qss = theme.build_qss(theme.LIGHT_TOKENS)
    # px 指定が残っていたら、OSごとの既定フォントの違いに追従できない
    for selector in ("QToolButton#collapsible_section_toggle",
                     "QToolButton#property_subsection_toggle"):
        import re
        block = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", qss).group(1)
        decl = re.search(r"font-size:\s*([^;]+);", block).group(1).strip()
        assert decl.endswith("pt"), f"{selector} の font-size が pt 指定でない: {decl}"


def test_only_the_first_section_omits_its_separator_rule(window):
    """区切りの罫線は各見出しの上に引くが、1本目だけは親見出しの直下なので
    二重線に見える。そこだけ引かない。"""
    first_key = DATASET_PROPERTY_SECTIONS[0][0]
    for key, _title in DATASET_PROPERTY_SECTIONS:
        toggle = window._prop_sections[key]['toggle']
        expected = True if key == first_key else None
        assert toggle.property("firstSection") == expected, key


def test_section_header_spans_the_full_width(window):
    """
    ★ QToolButton の既定は「文字幅ぴったり」で、そのままだと区切りの罫線が
    見出しの文字の下までしか引かれず、区切りとして機能しない。
    """
    from PySide6.QtWidgets import QSizePolicy
    for key, _title in DATASET_PROPERTY_SECTIONS:
        toggle = window._prop_sections[key]['toggle']
        assert toggle.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding, key
