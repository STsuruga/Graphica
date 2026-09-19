"""軸の設定: 画面の欄と設定の辞書の相互変換、サブプロットの行数と列数、フォントと色の選択。"""
import functools
import logging
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QFontDialog, QMessageBox

from graphica.core.axis_settings import axis_setting
from graphica.core.unit_conversion import X_AXIS_UNIT_CHOICES
from graphica.gui import theme
from graphica.gui.canvas import MINOR_TICK_LENGTH_AUTO
from graphica.gui.color_history import get_color_with_history
from graphica.gui.dialogs import LegendOrderDialog, LabelEditDialog

logger = logging.getLogger(__name__)


# Windows の「Arial Narrow」は matplotlib には family="Arial", stretch="condensed" として登録されていて、
# 名前のままでは見つからず黙って既定のフォントになる。末尾の語を stretch に読み替えて探し直す。
_FONT_STRETCH_KEYWORDS = {
    'narrow': 'condensed',
    'condensed': 'condensed',
    'semicondensed': 'semi-condensed',
    'extracondensed': 'extra-condensed',
    'ultracondensed': 'ultra-condensed',
    'wide': 'expanded',
    'expanded': 'expanded',
    'semiexpanded': 'semi-expanded',
    'extraexpanded': 'extra-expanded',
    'ultraexpanded': 'ultra-expanded',
}


@functools.lru_cache(maxsize=256)
def _resolve_font_family_for_matplotlib(family_name: str):
    """(matplotlib に渡す family, stretch または None, 解決できたか) を返す。

    軸の設定を変えるたびに呼ばれるので、findfont の結果をキャッシュする。
    """
    import matplotlib.font_manager as fm

    try:
        fm.findfont(fm.FontProperties(family=family_name), fallback_to_default=False)
        return family_name, None, True
    except ValueError:
        pass

    words = family_name.rsplit(None, 1)
    if len(words) == 2:
        base, suffix = words
        stretch = _FONT_STRETCH_KEYWORDS.get(suffix.lower())
        if stretch is not None:
            try:
                fm.findfont(fm.FontProperties(family=base, stretch=stretch), fallback_to_default=False)
                return base, stretch, True
            except ValueError:
                pass

    return family_name, None, False


def _qfont_from_family_props(font_props: dict) -> QFont:
    """'family' は候補のリストか、古いプロジェクトでは1つの名前。QFont(list) は無いので setFamilies() を使う。"""
    family = font_props.get('family', 'Sans Serif')
    if isinstance(family, (list, tuple)):
        font = QFont()
        if family:
            font.setFamilies(list(family))
        return font
    return QFont(family)


def _order_labels(labels, order):
    """order の順に並べ、order に無いラベルは元の順のまま末尾に置く。"""
    if not order:
        return list(labels)
    order_index = {name: i for i, name in enumerate(order)}
    indices = sorted(
        range(len(labels)),
        key=lambda i: (0, order_index[labels[i]]) if labels[i] in order_index else (1, i)
    )
    return [labels[i] for i in indices]


class SettingsMixin:
    def _on_layout_changed(self):
            if getattr(self.project, 'layout_mode', 'grid') == 'free':
                return

            # 欄の値を変える間、変更の通知が連鎖しないように
            self._block_all_signals(True)

            rows = self.subplot_rows_spinbox.value()
            cols = self.subplot_cols_spinbox.value()
            total_plots = rows * cols

            current_plot_count = len(self.project.all_plot_settings)

            if total_plots > current_plot_count:
                # 増えた分は今の軸の設定をもとにする
                default_settings = self._gather_settings_from_ui()
                for _ in range(total_plots - current_plot_count):
                    new_settings = default_settings.copy()
                    # 注釈は引き継がない。浅いコピーなので、空のリストにしないと全部が同じリストを共有する
                    new_settings['annotations'] = []
                    new_settings['legend_order'] = []
                    self.project.all_plot_settings.append(new_settings)

            elif total_plots < current_plot_count:
                self.project.all_plot_settings = self.project.all_plot_settings[:total_plots]

                # 無くなったサブプロットを描画先にしていたデータセットは、どこにも描かれず
                # エクスポートにも入らないのに気づけないので、最後のサブプロットに移す
                for dataset in self.project.datasets:
                    if dataset.subplot_target >= total_plots:
                        dataset.subplot_target = total_plots - 1

            if self.project.active_axis_index >= total_plots:
                self.project.active_axis_index = 0

            self._update_subplot_combos()
            self._apply_settings_to_ui_controls(self.project.all_plot_settings[self.project.active_axis_index])

            self._block_all_signals(False)

            self._update_plot()

    def _on_share_axis_changed(self):
        self.project.share_x_axis = self.share_x_checkbox.isChecked()
        self.project.share_y_axis = self.share_y_checkbox.isChecked()
        self._update_plot()

    def _on_active_axis_changed(self, index):
            """切り替える前の欄の値を元の軸に保存してから、新しい軸の設定を欄に読み込む。"""

            if index == -1 or index >= len(self.project.all_plot_settings):
                return

            self.project.all_plot_settings[self.project.active_axis_index] = self._gather_settings_from_ui()

            self.project.active_axis_index = index

            settings_to_load = self.project.all_plot_settings[self.project.active_axis_index]
            self._apply_settings_to_ui_controls(settings_to_load)

    def _on_axis_setting_changed(self):
            current_settings = self._gather_settings_from_ui()

            self.project.all_plot_settings[self.project.active_axis_index] = current_settings

            self._update_plot_appearance()

    def _update_subplot_combos(self):
            total_plots = len(self.project.all_plot_settings)
            plot_names = [f"プロット {i+1}" for i in range(total_plots)]

            self.active_axis_combo.blockSignals(True)
            self.subplot_target_combo.blockSignals(True)

            self.active_axis_combo.clear()
            self.subplot_target_combo.clear()

            self.active_axis_combo.addItems(plot_names)
            self.subplot_target_combo.addItems(plot_names)

            self.active_axis_combo.setCurrentIndex(self.project.active_axis_index)

            # 「描画先」の選択はデータセットを選んだときに property_panel.update_ui_state が決める
            self.active_axis_combo.blockSignals(False)
            self.subplot_target_combo.blockSignals(False)


    def _seed_min_max_spinboxes(self, min_spinbox, max_spinbox, limits):
        """オートスケールを切った瞬間に、いま表示している範囲を最小値・最大値の欄に入れる。

        欄が初期値 0/0 のままだと、最小値を先に変えたとき「最小 >= 最大」で反映されない。
        """
        if limits is None:
            return
        min_lim, max_lim = limits
        min_spinbox.blockSignals(True)
        max_spinbox.blockSignals(True)
        min_spinbox.setValue(min_lim)
        max_spinbox.setValue(max_lim)
        min_spinbox.blockSignals(False)
        max_spinbox.blockSignals(False)

    def _current_active_axis(self):
        axis_index = self.project.active_axis_index
        if 0 <= axis_index < len(self.canvas.all_axes):
            return self.canvas.all_axes[axis_index]
        return None

    def _refresh_x_autoscale_enabled_state(self):
        """最小値・最大値の欄の有効/無効だけをオートスケールに合わせる。値は書き換えない。

        保存した設定を戻すときはこちらを使う。_on_x_autoscale_changed() は表示中の範囲を欄に入れるので、
        保存されていた範囲が上書きされる。
        """
        is_autoscale = self.ui.x_autoscale_checkbox.isChecked()
        self.ui.x_min_spinbox.setEnabled(not is_autoscale)
        self.ui.x_max_spinbox.setEnabled(not is_autoscale)
        return is_autoscale

    def _refresh_y_autoscale_enabled_state(self):
        is_autoscale = self.ui.y_autoscale_checkbox.isChecked()
        self.ui.y_min_spinbox.setEnabled(not is_autoscale)
        self.ui.y_max_spinbox.setEnabled(not is_autoscale)
        return is_autoscale

    def _on_x_autoscale_changed(self):
        """利用者がチェックを変えたとき(設定を戻すときは _refresh_x_autoscale_enabled_state)。"""
        is_autoscale = self._refresh_x_autoscale_enabled_state()

        if not is_autoscale:
            axis = self._current_active_axis()
            self._seed_min_max_spinboxes(
                self.ui.x_min_spinbox, self.ui.x_max_spinbox, axis.get_xlim() if axis is not None else None)

        # 欄の値を書き換えたので、描き直すだけでなく設定も集め直す
        self._on_axis_setting_changed()

    def _on_y_autoscale_changed(self):
        is_autoscale = self._refresh_y_autoscale_enabled_state()

        if not is_autoscale:
            axis = self._current_active_axis()
            self._seed_min_max_spinboxes(
                self.ui.y_min_spinbox, self.ui.y_max_spinbox, axis.get_ylim() if axis is not None else None)

        self._on_axis_setting_changed()

    def _on_x_tick_mode_changed(self):
        is_fixed_interval = (self.ui.x_major_tick_mode_combo.currentIndex() == 1)
        self.ui.x_major_tick_interval_spinbox.setEnabled(is_fixed_interval)
        self._update_plot_appearance()

    def _on_y_tick_mode_changed(self):
        is_fixed_interval = (self.ui.y_major_tick_mode_combo.currentIndex() == 1)
        self.ui.y_major_tick_interval_spinbox.setEnabled(is_fixed_interval)
        self._update_plot_appearance()

    def _on_x_minor_tick_visibility_changed(self):
        """補助目盛の表示と対数表示の両方に依存するので、同じスロットで受ける。"""
        is_visible = self.ui.x_minor_ticks_visible_checkbox.isChecked()
        is_log = self.ui.x_log_checkbox.isChecked()
        # 対数軸は MultipleLocator ではなく LogLocator なので間隔は使わない
        self.ui.x_minor_tick_interval_spinbox.setEnabled(is_visible and not is_log)
        self.x_log_minor_subs_label.setVisible(is_log)
        self.x_log_minor_subs_combo.setVisible(is_log)
        self.x_log_minor_labels_checkbox.setVisible(is_log)
        self.x_log_minor_subs_combo.setEnabled(is_log and is_visible)
        self.x_log_minor_labels_checkbox.setEnabled(is_log and is_visible)
        self._update_plot_appearance()

    def _on_y_minor_tick_visibility_changed(self):
        is_visible = self.ui.y_minor_ticks_visible_checkbox.isChecked()
        is_log = self.ui.y_log_checkbox.isChecked()
        self.ui.y_minor_tick_interval_spinbox.setEnabled(is_visible and not is_log)
        self.y_log_minor_subs_label.setVisible(is_log)
        self.y_log_minor_subs_combo.setVisible(is_log)
        self.y_log_minor_labels_checkbox.setVisible(is_log)
        self.y_log_minor_subs_combo.setEnabled(is_log and is_visible)
        self.y_log_minor_labels_checkbox.setEnabled(is_log and is_visible)
        self._update_plot_appearance()

    def _on_legend_visibility_changed(self):
        is_visible = self.ui.legend_visible_checkbox.isChecked()

        self.legend_loc_label.setEnabled(is_visible)
        self.legend_loc_combo.setEnabled(is_visible)
        self.legend_font_label.setEnabled(is_visible)
        self.legend_font_button.setEnabled(is_visible)
        self.legend_color_label.setEnabled(is_visible)
        self.legend_color_button.setEnabled(is_visible)

        self._update_plot_appearance()


    def _grid_linestyle_code(self, combo_index: int) -> str:
        choices = self.grid_linestyle_choices
        if 0 <= combo_index < len(choices):
            return choices[combo_index][1]
        return '-'

    def _grid_linestyle_index(self, linestyle_code: str) -> int:
        """未知の値は 0(実線)。"""
        for i, (_label, code) in enumerate(self.grid_linestyle_choices):
            if code == linestyle_code:
                return i
        return 0

    def _on_grid_visibility_changed(self):
        is_visible = self.ui.grid_visible_checkbox.isChecked()

        self.ui.minor_grid_visible_checkbox.setEnabled(is_visible)

        # 主のグリッドの欄はグリッドの表示に、補助の欄はさらに補助グリッドの表示にも従う
        is_minor_visible = is_visible and self.ui.minor_grid_visible_checkbox.isChecked()
        for widget in (
            self.x_major_grid_linestyle_combo, self.x_major_grid_width_spinbox, self.x_major_grid_alpha_spinbox,
            self.y_major_grid_linestyle_combo, self.y_major_grid_width_spinbox, self.y_major_grid_alpha_spinbox,
        ):
            widget.setEnabled(is_visible)
        for widget in (
            self.x_minor_grid_linestyle_combo, self.x_minor_grid_width_spinbox, self.x_minor_grid_alpha_spinbox,
            self.y_minor_grid_linestyle_combo, self.y_minor_grid_width_spinbox, self.y_minor_grid_alpha_spinbox,
        ):
            widget.setEnabled(is_minor_visible)

        self._update_plot_appearance()


    def _warn_if_font_family_unavailable_for_graph(self, font):
        """グラフのフォントが matplotlib で見つからなければ知らせる(選択は保存する)。

        QFontDialog は OS のフォント一覧を出すが、matplotlib は別の一覧で探し、見つからないと黙って既定のフォントになる。
        """
        family = font.family()
        _resolved_name, _stretch, resolved = _resolve_font_family_for_matplotlib(family)
        if not resolved:
            QMessageBox.warning(
                self, "フォントが見つかりません",
                f"フォント「{family}」はグラフの描画エンジン(matplotlib)には認識されず、"
                "代わりに既定のフォントで表示されます。\n\n"
                "OS側のフォント一覧には表示されていても、グラフの描画には使えない"
                "フォントがあります。別のフォントをお試しください。"
            )

    def _on_change_tick_font(self):
        ok, font = QFontDialog.getFont(self._tick_font, self)
        if ok:
            self._warn_if_font_family_unavailable_for_graph(font)
            self._tick_font = font
            self._on_axis_setting_changed()

    def _on_change_tick_color(self):
        color = get_color_with_history(self.settings, self)
        if color.isValid():
            self._tick_color = color.name()
            self._on_axis_setting_changed()

    def _on_change_axis_label_font(self):
        ok, font = QFontDialog.getFont(self._axis_label_font, self)
        if ok:
            self._warn_if_font_family_unavailable_for_graph(font)
            self._axis_label_font = font
            # _update_plot_appearance() だけでは all_plot_settings に保存されない
            self._on_axis_setting_changed()

    def _on_change_axis_label_color(self):
        color = get_color_with_history(self.settings, self)
        if color.isValid():
            self._axis_label_color = color.name()
            self._on_axis_setting_changed()

    def _on_change_legend_font(self):
        ok, font = QFontDialog.getFont(self._legend_font, self)
        if ok:
            self._warn_if_font_family_unavailable_for_graph(font)
            self._legend_font = font
            self._on_axis_setting_changed()

    def _on_change_legend_color(self):
        color = get_color_with_history(self.settings, self)
        if color.isValid():
            self._legend_color = color.name()
            self._on_axis_setting_changed()

    def _on_change_spine_color(self):
        color = get_color_with_history(self.settings, self)
        if color.isValid():
            self._spine_color = color.name()
            self._on_axis_setting_changed()

    def _open_label_edit_dialog(self, line_edit, dialog_title):
        """編集ダイアログの結果を line_edit に setText() する(textChanged からいつもの経路で反映される)。

        LABEL_SYMBOL_PALETTE は main_window がこの mixin を import しているので、ここで遅れて import する。
        """
        from graphica.gui.main_window import LABEL_SYMBOL_PALETTE

        dialog = LabelEditDialog(line_edit.text(), dialog_title, LABEL_SYMBOL_PALETTE, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            line_edit.setText(dialog.get_text())

    def _refresh_label_preview(self, preview_label, text, placeholder):
        """プレビューを matplotlib で描いた見た目にする。空なら placeholder を text_muted の色で出す。"""
        from graphica.gui.mathtext_preview import render_mathtext_to_pixmap

        tokens = theme.current_tokens()
        if text:
            pixmap = render_mathtext_to_pixmap(text, color=tokens["text_primary"])
        else:
            pixmap = render_mathtext_to_pixmap(placeholder, color=tokens["text_muted"])
        # 欄の幅が決まるたびに収まるよう縮める(setPixmap だと、この時点の幅がまだ確定していないとはみ出す)
        preview_label.set_natural_pixmap(pixmap)

    def _refresh_all_label_previews(self):
        """文字色がテーマに従うので、ダークモードの切り替えで描き直す。"""
        for preview_label, line_edit, placeholder in self._label_preview_widgets:
            self._refresh_label_preview(preview_label, line_edit.text(), placeholder)

    def _on_legend_loc_changed(self, *_args):
        """ドラッグした位置(legend_position)が残っていると選んだ位置が効かないので消す。"""
        axis_index = self.project.active_axis_index
        if axis_index < len(self.project.all_plot_settings):
            self.project.all_plot_settings[axis_index].pop('legend_position', None)
        self._on_axis_setting_changed()

    def _on_legend_drag_release(self, _event):
        """凡例のドラッグは matplotlib 側の button_release_event で確定し、こちらが先に呼ばれうるので、処理の後で読む。"""
        QTimer.singleShot(0, self._store_dragged_legend_positions)

    def _store_dragged_legend_positions(self):
        """凡例がドラッグで置かれていれば、その位置を legend_position に保存する(しないと次の描画で戻る)。どれか変えたら True。"""
        changed = False
        settings_list = self.project.all_plot_settings
        secondary_axes = getattr(self.canvas, 'all_secondary_axes', [])
        for index, ax in enumerate(getattr(self.canvas, 'all_axes', [])):
            if index >= len(settings_list):
                break
            legend = ax.get_legend()
            if legend is None and index < len(secondary_axes) and secondary_axes[index] is not None:
                legend = secondary_axes[index].get_legend()
            loc = getattr(legend, '_loc', None) if legend is not None else None
            if not isinstance(loc, tuple) or len(loc) != 2:
                continue
            position = [round(float(loc[0]), 4), round(float(loc[1]), 4)]
            if axis_setting(settings_list[index], 'legend_position') != position:
                settings_list[index]['legend_position'] = position
                changed = True
        return changed

    def _on_edit_legend_order(self):
        """今の軸の凡例の並びをダイアログで決め、legend_order に保存する。"""
        axis_index = self.project.active_axis_index
        if axis_index >= len(self.canvas.all_axes):
            return
        ax = self.canvas.all_axes[axis_index]
        _, labels = ax.get_legend_handles_labels()
        if axis_index < len(self.canvas.all_secondary_axes) and self.canvas.all_secondary_axes[axis_index] is not None:
            _, secondary_labels = self.canvas.all_secondary_axes[axis_index].get_legend_handles_labels()
            labels = labels + secondary_labels
        if not labels:
            QMessageBox.information(self, "凡例の順序", "この軸には凡例に表示するデータセットがありません。")
            return

        current_order = axis_setting(self.project.all_plot_settings[axis_index], 'legend_order') or []
        dialog = LegendOrderDialog(_order_labels(labels, current_order), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.project.all_plot_settings[axis_index]['legend_order'] = dialog.get_order()
        self._update_plot()

    # 下の2つは呼ばれない(valueChanged は _on_axis_setting_changed に直接つないでいる)

    def _on_tick_width_changed(self, value):
        self._tick_width = value
        self._update_plot_appearance()

    def _on_spine_width_changed(self, value):
        self._spine_width = value
        self._update_plot_appearance()

    def _font_props_to_dict(self, qfont: QFont) -> dict:
        """QFont を JSON に保存できる辞書にする。

        'family' は families() の候補リストのまま保存する(.family() の先頭1つにすると、macOS に無い
        "Yu Gothic" だけが残って日本語が化ける)。各候補は _resolve_font_family_for_matplotlib で解決する。
        """
        resolved_families = []
        stretch = None
        for name in qfont.families():
            resolved_name, resolved_stretch, _ok = _resolve_font_family_for_matplotlib(name)
            resolved_families.append(resolved_name)
            if stretch is None and resolved_stretch is not None:
                stretch = resolved_stretch

        result = {
            'family': resolved_families,
            'size': qfont.pointSize(),
            'weight': 'bold' if qfont.bold() else 'normal',
            'style': 'italic' if qfont.italic() else 'normal'
        }
        if stretch is not None:
            result['stretch'] = stretch
        return result

    def _gather_settings_from_ui(self) -> dict:
        """今の軸の設定を、画面の欄から集めた辞書(保存形式そのもの)で返す。キーは AXIS_SETTING_DEFAULTS と同じ。"""
        settings = {
            'title': self.ui.title_text_edit.text(),
            'x_label': self.ui.x_label_text_edit.text(),
            'y_label': self.ui.y_label_text_edit.text(),
            'x_label_visible': self.x_label_visible_checkbox.isChecked(),
            'y_label_visible': self.y_label_visible_checkbox.isChecked(),
            'y2_label': self.y2_label_text_edit.text(),

            'x_autoscale': self.ui.x_autoscale_checkbox.isChecked(),
            'x_min': self.ui.x_min_spinbox.value(),
            'x_max': self.ui.x_max_spinbox.value(),
            'x_log': self.ui.x_log_checkbox.isChecked(),
            'x_invert': self.ui.x_invert_checkbox.isChecked(),
            'x_major_tick_mode': self.ui.x_major_tick_mode_combo.currentIndex(),
            'x_major_tick_interval': self.ui.x_major_tick_interval_spinbox.value(),
            'x_minor_ticks_visible': self.ui.x_minor_ticks_visible_checkbox.isChecked(),
            'x_minor_tick_interval': self.ui.x_minor_tick_interval_spinbox.value(),
            # 対数軸のときだけ効く
            'x_log_minor_subs': self.x_log_minor_subs_combo.currentData(),
            'x_log_minor_labels': self.x_log_minor_labels_checkbox.isChecked(),
            'x_tick_format_mode': self.x_tick_format_combo.currentIndex(),
            'x_tick_decimals': self.x_tick_decimals_spinbox.value(),
            'x_secondary_axis_source_unit':
                X_AXIS_UNIT_CHOICES[self.x_secondary_axis_source_unit_combo.currentIndex()],
            'x_secondary_axis_target_unit':
                X_AXIS_UNIT_CHOICES[self.x_secondary_axis_target_unit_combo.currentIndex()],

            'y_autoscale': self.ui.y_autoscale_checkbox.isChecked(),
            'y_min': self.ui.y_min_spinbox.value(),
            'y_max': self.ui.y_max_spinbox.value(),
            'y_log': self.ui.y_log_checkbox.isChecked(),
            'y_invert': self.ui.y_invert_checkbox.isChecked(),
            'y_major_tick_mode': self.ui.y_major_tick_mode_combo.currentIndex(),
            'y_major_tick_interval': self.ui.y_major_tick_interval_spinbox.value(),
            'y_minor_ticks_visible': self.ui.y_minor_ticks_visible_checkbox.isChecked(),
            'y_minor_tick_interval': self.ui.y_minor_tick_interval_spinbox.value(),
            'y_log_minor_subs': self.y_log_minor_subs_combo.currentData(),
            'y_log_minor_labels': self.y_log_minor_labels_checkbox.isChecked(),
            'y_tick_format_mode': self.y_tick_format_combo.currentIndex(),
            'y_tick_decimals': self.y_tick_decimals_spinbox.value(),

            'legend_visible': self.ui.legend_visible_checkbox.isChecked(),
            'legend_loc': self.legend_loc_combo.currentText(),
            'grid_visible': self.ui.grid_visible_checkbox.isChecked(),
            'minor_grid_visible': self.ui.minor_grid_visible_checkbox.isChecked(),

            'x_major_grid_linestyle': self._grid_linestyle_code(self.x_major_grid_linestyle_combo.currentIndex()),
            'x_major_grid_width': self.x_major_grid_width_spinbox.value(),
            'x_major_grid_alpha': self.x_major_grid_alpha_spinbox.value(),
            'x_minor_grid_linestyle': self._grid_linestyle_code(self.x_minor_grid_linestyle_combo.currentIndex()),
            'x_minor_grid_width': self.x_minor_grid_width_spinbox.value(),
            'x_minor_grid_alpha': self.x_minor_grid_alpha_spinbox.value(),
            'y_major_grid_linestyle': self._grid_linestyle_code(self.y_major_grid_linestyle_combo.currentIndex()),
            'y_major_grid_width': self.y_major_grid_width_spinbox.value(),
            'y_major_grid_alpha': self.y_major_grid_alpha_spinbox.value(),
            'y_minor_grid_linestyle': self._grid_linestyle_code(self.y_minor_grid_linestyle_combo.currentIndex()),
            'y_minor_grid_width': self.y_minor_grid_width_spinbox.value(),
            'y_minor_grid_alpha': self.y_minor_grid_alpha_spinbox.value(),
            'major_tick_direction': self.major_tick_direction_combo.currentText(),
            'minor_tick_direction': self.minor_tick_direction_combo.currentText(),
            'major_tick_direction_y2': self.major_tick_direction_y2_combo.currentText(),
            'minor_tick_direction_y2': self.minor_tick_direction_y2_combo.currentText(),
            'x_ticks_visible': self.x_ticks_visible_checkbox.isChecked(),
            'x_tick_labels_visible': self.x_tick_labels_visible_checkbox.isChecked(),
            'y_ticks_visible': self.y_ticks_visible_checkbox.isChecked(),
            'y_tick_labels_visible': self.y_tick_labels_visible_checkbox.isChecked(),

            'tick_font': self._font_props_to_dict(self._tick_font),
            'tick_color': self._tick_color,
            'tick_width': self.ui.tick_width_spinbox.value(),
            'major_tick_length': self.major_tick_length_spinbox.value(),
            # 負値(スピンボックスの「自動」)は -1 に正規化して保存する
            'minor_tick_length': (self.minor_tick_length_spinbox.value()
                                  if self.minor_tick_length_spinbox.value() >= 0 else -1),
            'axis_label_font': self._font_props_to_dict(self._axis_label_font),
            'axis_label_color': self._axis_label_color,
            'legend_font': self._font_props_to_dict(self._legend_font),
            'legend_color': self._legend_color,
            'spine_width': self.ui.spine_width_spinbox.value(),
            'spine_color': self._spine_color,

            # 2Dマップが無い軸では効かない
            'colorbar_enabled': self.colorbar_enabled_checkbox.isChecked(),
            'colorbar_position': self.colorbar_position_combo.currentData(),
            'colorbar_width_fraction': self.colorbar_width_spinbox.value(),
            'colorbar_label': self.colorbar_label_edit.text(),
        }

        # 欄を持たず操作から直接書き込まれるもの。辞書は丸ごと入れ替わるので、引き継がないと消える。
        if self.project.active_axis_index < len(self.project.all_plot_settings):
            current = self.project.all_plot_settings[self.project.active_axis_index]
            settings['annotations'] = axis_setting(current, 'annotations')
            settings['legend_order'] = axis_setting(current, 'legend_order')
            settings['free_rect'] = axis_setting(current, 'free_rect')
            settings['legend_position'] = axis_setting(current, 'legend_position')
        else:
            settings['annotations'] = []
            settings['legend_order'] = []
            settings['free_rect'] = None
            settings['legend_position'] = None
        return settings

    def _apply_settings_to_ui_controls(self, settings: dict):
        """設定の辞書を画面の欄に戻す。無いキーは AXIS_SETTING_DEFAULTS の既定値になる。"""
        try:
            # 欄に値を入れる間は、変更の通知で設定を書き換えないようにする
            self._block_all_signals(True)

            self.ui.title_text_edit.setText(axis_setting(settings, 'title'))
            self.ui.x_label_text_edit.setText(axis_setting(settings, 'x_label'))
            self.ui.y_label_text_edit.setText(axis_setting(settings, 'y_label'))
            self.x_label_visible_checkbox.setChecked(axis_setting(settings, 'x_label_visible'))
            self.y_label_visible_checkbox.setChecked(axis_setting(settings, 'y_label_visible'))
            self.y2_label_text_edit.setText(axis_setting(settings, 'y2_label'))

            self.ui.x_autoscale_checkbox.setChecked(axis_setting(settings, 'x_autoscale'))
            self.ui.x_min_spinbox.setValue(axis_setting(settings, 'x_min'))
            self.ui.x_max_spinbox.setValue(axis_setting(settings, 'x_max'))
            self.ui.x_log_checkbox.setChecked(axis_setting(settings, 'x_log'))
            self.ui.x_invert_checkbox.setChecked(axis_setting(settings, 'x_invert'))
            self.ui.x_major_tick_mode_combo.setCurrentIndex(axis_setting(settings, 'x_major_tick_mode'))
            self.ui.x_major_tick_interval_spinbox.setValue(axis_setting(settings, 'x_major_tick_interval'))
            self.ui.x_minor_ticks_visible_checkbox.setChecked(axis_setting(settings, 'x_minor_ticks_visible'))
            self.ui.x_minor_tick_interval_spinbox.setValue(axis_setting(settings, 'x_minor_tick_interval'))
            _x_log_minor_subs_idx = self.x_log_minor_subs_combo.findData(axis_setting(settings, 'x_log_minor_subs'))
            self.x_log_minor_subs_combo.setCurrentIndex(_x_log_minor_subs_idx if _x_log_minor_subs_idx != -1 else 0)
            self.x_log_minor_labels_checkbox.setChecked(axis_setting(settings, 'x_log_minor_labels'))
            self.x_tick_format_combo.setCurrentIndex(axis_setting(settings, 'x_tick_format_mode'))
            self.x_tick_decimals_spinbox.setValue(axis_setting(settings, 'x_tick_decimals'))
            _source_unit = axis_setting(settings, 'x_secondary_axis_source_unit')
            self.x_secondary_axis_source_unit_combo.setCurrentIndex(
                X_AXIS_UNIT_CHOICES.index(_source_unit) if _source_unit in X_AXIS_UNIT_CHOICES else 0)
            _target_unit = axis_setting(settings, 'x_secondary_axis_target_unit')
            self.x_secondary_axis_target_unit_combo.setCurrentIndex(
                X_AXIS_UNIT_CHOICES.index(_target_unit) if _target_unit in X_AXIS_UNIT_CHOICES else 0)

            self.ui.y_autoscale_checkbox.setChecked(axis_setting(settings, 'y_autoscale'))
            self.ui.y_min_spinbox.setValue(axis_setting(settings, 'y_min'))
            self.ui.y_max_spinbox.setValue(axis_setting(settings, 'y_max'))
            self.ui.y_log_checkbox.setChecked(axis_setting(settings, 'y_log'))
            self.ui.y_invert_checkbox.setChecked(axis_setting(settings, 'y_invert'))
            self.ui.y_major_tick_mode_combo.setCurrentIndex(axis_setting(settings, 'y_major_tick_mode'))
            self.ui.y_major_tick_interval_spinbox.setValue(axis_setting(settings, 'y_major_tick_interval'))
            self.ui.y_minor_ticks_visible_checkbox.setChecked(axis_setting(settings, 'y_minor_ticks_visible'))
            self.ui.y_minor_tick_interval_spinbox.setValue(axis_setting(settings, 'y_minor_tick_interval'))
            _y_log_minor_subs_idx = self.y_log_minor_subs_combo.findData(axis_setting(settings, 'y_log_minor_subs'))
            self.y_log_minor_subs_combo.setCurrentIndex(_y_log_minor_subs_idx if _y_log_minor_subs_idx != -1 else 0)
            self.y_log_minor_labels_checkbox.setChecked(axis_setting(settings, 'y_log_minor_labels'))
            self.y_tick_format_combo.setCurrentIndex(axis_setting(settings, 'y_tick_format_mode'))
            self.y_tick_decimals_spinbox.setValue(axis_setting(settings, 'y_tick_decimals'))

            self.ui.legend_visible_checkbox.setChecked(axis_setting(settings, 'legend_visible'))
            self.legend_loc_combo.setCurrentText(axis_setting(settings, 'legend_loc'))
            self.ui.grid_visible_checkbox.setChecked(axis_setting(settings, 'grid_visible'))
            self.ui.minor_grid_visible_checkbox.setChecked(axis_setting(settings, 'minor_grid_visible'))

            self.x_major_grid_linestyle_combo.setCurrentIndex(
                self._grid_linestyle_index(axis_setting(settings, 'x_major_grid_linestyle')))
            self.x_major_grid_width_spinbox.setValue(axis_setting(settings, 'x_major_grid_width'))
            self.x_major_grid_alpha_spinbox.setValue(axis_setting(settings, 'x_major_grid_alpha'))
            self.x_minor_grid_linestyle_combo.setCurrentIndex(
                self._grid_linestyle_index(axis_setting(settings, 'x_minor_grid_linestyle')))
            self.x_minor_grid_width_spinbox.setValue(axis_setting(settings, 'x_minor_grid_width'))
            self.x_minor_grid_alpha_spinbox.setValue(axis_setting(settings, 'x_minor_grid_alpha'))
            self.y_major_grid_linestyle_combo.setCurrentIndex(
                self._grid_linestyle_index(axis_setting(settings, 'y_major_grid_linestyle')))
            self.y_major_grid_width_spinbox.setValue(axis_setting(settings, 'y_major_grid_width'))
            self.y_major_grid_alpha_spinbox.setValue(axis_setting(settings, 'y_major_grid_alpha'))
            self.y_minor_grid_linestyle_combo.setCurrentIndex(
                self._grid_linestyle_index(axis_setting(settings, 'y_minor_grid_linestyle')))
            self.y_minor_grid_width_spinbox.setValue(axis_setting(settings, 'y_minor_grid_width'))
            self.y_minor_grid_alpha_spinbox.setValue(axis_setting(settings, 'y_minor_grid_alpha'))
            self.major_tick_direction_combo.setCurrentText(axis_setting(settings, 'major_tick_direction'))
            self.minor_tick_direction_combo.setCurrentText(axis_setting(settings, 'minor_tick_direction'))
            self.major_tick_direction_y2_combo.setCurrentText(axis_setting(settings, 'major_tick_direction_y2'))
            self.minor_tick_direction_y2_combo.setCurrentText(axis_setting(settings, 'minor_tick_direction_y2'))
            self.x_ticks_visible_checkbox.setChecked(axis_setting(settings, 'x_ticks_visible'))
            self.x_tick_labels_visible_checkbox.setChecked(
                axis_setting(settings, 'x_tick_labels_visible'))
            self.y_ticks_visible_checkbox.setChecked(axis_setting(settings, 'y_ticks_visible'))
            self.y_tick_labels_visible_checkbox.setChecked(
                axis_setting(settings, 'y_tick_labels_visible'))

            tick_font_props = axis_setting(settings, 'tick_font')
            self._tick_font = _qfont_from_family_props(tick_font_props)
            self._tick_font.setPointSize(tick_font_props.get('size', 10))
            self._tick_font.setBold(tick_font_props.get('weight') == 'bold')
            self._tick_font.setItalic(tick_font_props.get('style') == 'italic')

            label_font_props = axis_setting(settings, 'axis_label_font')
            self._axis_label_font = _qfont_from_family_props(label_font_props)
            self._axis_label_font.setPointSize(label_font_props.get('size', 10))
            self._axis_label_font.setBold(label_font_props.get('weight') == 'bold')
            self._axis_label_font.setItalic(label_font_props.get('style') == 'italic')

            legend_font_props = axis_setting(settings, 'legend_font')
            self._legend_font = _qfont_from_family_props(legend_font_props)
            if 'size' in legend_font_props:
                self._legend_font.setPointSize(legend_font_props.get('size', 10))
            self._legend_font.setBold(legend_font_props.get('weight') == 'bold')
            self._legend_font.setItalic(legend_font_props.get('style') == 'italic')

            self._tick_color = axis_setting(settings, 'tick_color')
            self._tick_width = axis_setting(settings, 'tick_width')
            self.ui.tick_width_spinbox.setValue(self._tick_width)
            self.major_tick_length_spinbox.setValue(axis_setting(settings, 'major_tick_length'))
            minor_tick_length = axis_setting(settings, 'minor_tick_length')
            self.minor_tick_length_spinbox.setValue(
                MINOR_TICK_LENGTH_AUTO if minor_tick_length is None or minor_tick_length < 0 else minor_tick_length)

            self._axis_label_color = axis_setting(settings, 'axis_label_color')
            self._legend_color = axis_setting(settings, 'legend_color')

            self._spine_width = axis_setting(settings, 'spine_width')
            self.ui.spine_width_spinbox.setValue(self._spine_width)
            self._spine_color = axis_setting(settings, 'spine_color')

            self.colorbar_enabled_checkbox.setChecked(axis_setting(settings, 'colorbar_enabled'))
            _cb_position = axis_setting(settings, 'colorbar_position')
            _cb_position_index = self.colorbar_position_combo.findData(_cb_position)
            self.colorbar_position_combo.setCurrentIndex(_cb_position_index if _cb_position_index != -1 else 0)
            self.colorbar_width_spinbox.setValue(axis_setting(settings, 'colorbar_width_fraction'))
            self.colorbar_label_edit.setText(axis_setting(settings, 'colorbar_label'))

            # 復元では _on_x_autoscale_changed(今の表示範囲を欄に入れる)を呼ばない。
            # 呼ぶと、オートスケールを切って保存した範囲が今の表示範囲で上書きされる。
            self._refresh_x_autoscale_enabled_state()
            self._refresh_y_autoscale_enabled_state()
            self._on_x_tick_mode_changed()
            self._on_y_tick_mode_changed()
            self._on_x_minor_tick_visibility_changed()
            self._on_y_minor_tick_visibility_changed()
            self._on_legend_visibility_changed()
            self._on_grid_visibility_changed()

        except Exception as e:
            QMessageBox.warning(self, "設定適用エラー", f"設定の適用中にエラーが発生しました:\n{e}")
            logger.exception("設定の適用中にエラー")
        finally:
            # 途中で失敗しても必ず戻す
            self._block_all_signals(False)

    def _block_all_signals(self, block: bool):
        self.ui.x_autoscale_checkbox.blockSignals(block)
        self.ui.x_min_spinbox.blockSignals(block)
        self.ui.x_max_spinbox.blockSignals(block)
        self.ui.x_log_checkbox.blockSignals(block)
        self.ui.x_invert_checkbox.blockSignals(block)
        self.ui.x_major_tick_mode_combo.blockSignals(block)
        self.ui.x_major_tick_interval_spinbox.blockSignals(block)
        self.ui.x_minor_ticks_visible_checkbox.blockSignals(block)
        self.ui.x_minor_tick_interval_spinbox.blockSignals(block)
        self.x_log_minor_subs_combo.blockSignals(block)
        self.x_log_minor_labels_checkbox.blockSignals(block)
        self.x_tick_format_combo.blockSignals(block)
        self.x_tick_decimals_spinbox.blockSignals(block)
        self.x_ticks_visible_checkbox.blockSignals(block)
        self.x_tick_labels_visible_checkbox.blockSignals(block)
        self.x_secondary_axis_source_unit_combo.blockSignals(block)
        self.x_secondary_axis_target_unit_combo.blockSignals(block)

        self.ui.y_autoscale_checkbox.blockSignals(block)
        self.ui.y_min_spinbox.blockSignals(block)
        self.ui.y_max_spinbox.blockSignals(block)
        self.ui.y_log_checkbox.blockSignals(block)
        self.ui.y_invert_checkbox.blockSignals(block)
        self.ui.y_major_tick_mode_combo.blockSignals(block)
        self.ui.y_major_tick_interval_spinbox.blockSignals(block)
        self.ui.y_minor_ticks_visible_checkbox.blockSignals(block)
        self.ui.y_minor_tick_interval_spinbox.blockSignals(block)
        self.y_log_minor_subs_combo.blockSignals(block)
        self.y_log_minor_labels_checkbox.blockSignals(block)
        self.y_tick_format_combo.blockSignals(block)
        self.y_tick_decimals_spinbox.blockSignals(block)
        self.y_ticks_visible_checkbox.blockSignals(block)
        self.y_tick_labels_visible_checkbox.blockSignals(block)

        self.ui.title_text_edit.blockSignals(block)
        self.ui.x_label_text_edit.blockSignals(block)
        self.ui.y_label_text_edit.blockSignals(block)
        self.x_label_visible_checkbox.blockSignals(block)
        self.y_label_visible_checkbox.blockSignals(block)
        self.y2_label_text_edit.blockSignals(block)
        self.ui.tick_font_button.blockSignals(block)
        self.ui.tick_color_button.blockSignals(block)
        self.ui.tick_width_spinbox.blockSignals(block)
        self.major_tick_length_spinbox.blockSignals(block)
        self.minor_tick_length_spinbox.blockSignals(block)
        self.ui.axis_label_font_button.blockSignals(block)
        self.ui.axis_label_color_button.blockSignals(block)
        self.legend_font_button.blockSignals(block)
        self.legend_color_button.blockSignals(block)
        self.ui.legend_visible_checkbox.blockSignals(block)
        self.legend_loc_combo.blockSignals(block)
        self.ui.grid_visible_checkbox.blockSignals(block)
        self.ui.minor_grid_visible_checkbox.blockSignals(block)
        self.x_major_grid_linestyle_combo.blockSignals(block)
        self.x_major_grid_width_spinbox.blockSignals(block)
        self.x_major_grid_alpha_spinbox.blockSignals(block)
        self.x_minor_grid_linestyle_combo.blockSignals(block)
        self.x_minor_grid_width_spinbox.blockSignals(block)
        self.x_minor_grid_alpha_spinbox.blockSignals(block)
        self.y_major_grid_linestyle_combo.blockSignals(block)
        self.y_major_grid_width_spinbox.blockSignals(block)
        self.y_major_grid_alpha_spinbox.blockSignals(block)
        self.y_minor_grid_linestyle_combo.blockSignals(block)
        self.y_minor_grid_width_spinbox.blockSignals(block)
        self.y_minor_grid_alpha_spinbox.blockSignals(block)
        self.ui.spine_width_spinbox.blockSignals(block)
        self.ui.spine_color_button.blockSignals(block)
        self.major_tick_direction_combo.blockSignals(block)
        self.minor_tick_direction_combo.blockSignals(block)
        self.major_tick_direction_y2_combo.blockSignals(block)
        self.minor_tick_direction_y2_combo.blockSignals(block)
        self.colorbar_enabled_checkbox.blockSignals(block)
        self.colorbar_position_combo.blockSignals(block)
        self.colorbar_width_spinbox.blockSignals(block)
        self.colorbar_label_edit.blockSignals(block)
