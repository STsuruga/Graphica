# gui/mixins/settings_mixin.py
"""
プロット(軸)の外観設定に関する処理をまとめた Mixin。
- レイアウト(行数/列数)、編集対象プロットの切り替え
- UI <-> settings辞書 の相互変換 (_gather_settings_from_ui / _apply_settings_to_ui_controls)
- フォント/色選択ダイアログ
- 各種チェックボックス変更に伴うUIの有効/無効切り替え
"""
import logging
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QFontDialog, QColorDialog, QMessageBox

from core.i18n import tr
from core.unit_conversion import X_AXIS_UNIT_CHOICES, X_AXIS_UNIT_NONE
from gui import theme
from gui.color_history import get_color_with_history
from gui.dialogs import LegendOrderDialog, LabelEditDialog

logger = logging.getLogger(__name__)


def _qfont_from_family_props(font_props: dict) -> QFont:
    """
    保存済みフォント辞書の'family'からQFontを復元する。

    'family'は新形式ではフォールバック候補のリスト(_font_props_to_dict参照)、
    旧形式(このリスト化より前に保存されたプロジェクトファイル)では単一の
    フォント名(str)。QFont(list)は使えないため、リストならsetFamilies()、
    strならQFont(str)相当のコンストラクタで復元する。
    """
    family = font_props.get('family', 'Sans Serif')
    if isinstance(family, (list, tuple)):
        font = QFont()
        if family:
            font.setFamilies(list(family))
        return font
    return QFont(family)


def _order_labels(labels, order):
    """凡例ラベルのリストを、保存済みの並び順(order)に従って並べ替える。
    order に無いラベルは元の相対順を保ったまま末尾に追加する。"""
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
            """
            サブプロットのレイアウト(行数/列数)スピンボックスが変更されたときに呼び出されます。
            all_plot_settings リストのサイズを調整し、UIを更新します。

            自由配置レイアウト(項目37)が有効な間は行数/列数スピンボックス自体が
            無効化されているが、念のため二重チェックとしてここでも早期returnする
            (自由配置モードでのサブプロット数の増減は「+」「-」ボタン経由で行う)。
            """
            if getattr(self.project, 'layout_mode', 'grid') == 'free':
                return

            # 1. 【★ 重要 ★】
            #    これからUIコントロール（active_axis_comboなど）の値を変更するため、
            #    シグナルの連鎖的な発火（ループ）を防ぐために一時的にブロックします。
            self._block_all_signals(True)

            rows = self.subplot_rows_spinbox.value()
            cols = self.subplot_cols_spinbox.value()
            total_plots = rows * cols # 新しいプロットの総数

            # 2. 既存のプロット設定リストのサイズを新しいサイズに合わせる
            current_plot_count = len(self.project.all_plot_settings)

            if total_plots > current_plot_count:
                # 2a. プロットが増えた場合
                #     現在のUI設定 (アクティブな軸の設定) をコピー元として取得
                default_settings = self._gather_settings_from_ui()
                for _ in range(total_plots - current_plot_count):
                    # ★ .copy() が重要 (辞書は参照型のため、コピーしないとすべて同じ設定になる)
                    new_settings = default_settings.copy()
                    # ★ 新しいサブプロットは、アクティブな軸の注釈をそのまま
                    # 引き継がず空から始める(かつ .copy() は浅いコピーなので、
                    # 空リストにしないと全ての新規プロットが同じリストを共有してしまう)
                    new_settings['annotations'] = []
                    new_settings['legend_order'] = []
                    self.project.all_plot_settings.append(new_settings)

            elif total_plots < current_plot_count:
                # 2b. プロットが減った場合
                #     リストの末尾から設定を削除
                self.project.all_plot_settings = self.project.all_plot_settings[:total_plots]

                # ★ バグ修正: 削除された(存在しなくなった)サブプロット番号を
                # subplot_target に持つデータセットは、そのままだと
                # gui/canvas.pyのdatasets-per-axisフィルタ(ds.subplot_target
                # == axis_index)に一致する軸が無くなり、どのサブプロットにも
                # 描画されず、エクスポート画像にも含まれなくなる。データ
                # セット自体はリストに残り続け普通に選択・編集できてしまう
                # ため、「データが消えた」ことに気づきにくいサイレントな
                # バグだった(グリッドを再び広げると何事もなかったかのように
                # 復活するため、原因の特定はさらに難しい)。存在する最後の
                # サブプロットに割り当て直すことで、見えなくなることを防ぐ。
                for dataset in self.project.datasets:
                    if dataset.subplot_target >= total_plots:
                        dataset.subplot_target = total_plots - 1

            # 3. アクティブな軸のインデックスが範囲外になったら 0 に戻す
            #    (例: 2x2=4 で P4 を編集中に 1x1=1 に変更した場合)
            if self.project.active_axis_index >= total_plots:
                self.project.active_axis_index = 0

            # 4. UIコントロールを更新
            #    コンボボックスの選択肢を (P1, P2...) のように更新
            self._update_subplot_combos()
            #    新しいアクティブインデックス (self.project.active_axis_index) の設定をUIにロード
            self._apply_settings_to_ui_controls(self.project.all_plot_settings[self.project.active_axis_index])

            # 5. シグナルのブロックを解除
            self._block_all_signals(False)

            # 6. グラフ全体を再描画
            self._update_plot()

    def _on_share_axis_changed(self):
        """
        「X軸を共有」「Y軸を共有」チェックボックスが変更されたときに呼び出されます。
        グリッドレイアウト時のみ意味を持つ設定のため、ProjectModel にそのまま保存し再描画します。
        """
        self.project.share_x_axis = self.share_x_checkbox.isChecked()
        self.project.share_y_axis = self.share_y_checkbox.isChecked()
        self._update_plot()

    def _on_active_axis_changed(self, index):
            """
            「編集対象のプロット」コンボボックスが変更されたときに呼び出されます。
            UI上の変更を古い軸設定に「保存」し、新しい軸設定をUIに「ロード」します。

            Args:
                index (int): 新しく選択されたコンボボックスのインデックス (＝軸インデックス)。
            """

            if index == -1 or index >= len(self.project.all_plot_settings):
                return # 無効なインデックス (例: リストクリア時)

            # 1. 【保存】
            #    変更「前」のUI設定を、変更「前」の active_axis_index に対応する
            #    設定リスト (all_plot_settings) に保存します。
            self.project.all_plot_settings[self.project.active_axis_index] = self._gather_settings_from_ui()

            # 2. 【更新】
            #    アクティブインデックスを新しいインデックスに更新します。
            self.project.active_axis_index = index

            # 3. 【ロード】
            #    新しくアクティブになったインデックスの設定をリストから取得し、
            #    その内容をUIコントロール（スピンボックス、テキストなど）に反映させます。
            settings_to_load = self.project.all_plot_settings[self.project.active_axis_index]
            self._apply_settings_to_ui_controls(settings_to_load)

    def _on_axis_setting_changed(self):
            """
            軸設定のUIコントロール(スピンボックス、テキストエディットなど)が
            変更されたときに呼び出されます。

            (_connect_signals で多くのUIがこのスロットに接続されています)
            """

            # 1. 現在のUIコントロールの状態をすべて辞書として収集
            current_settings = self._gather_settings_from_ui()

            # 2. 収集した設定を、現在アクティブな軸 (active_axis_index) の
            #    設定としてリスト (all_plot_settings) に「保存」します。
            self.project.all_plot_settings[self.project.active_axis_index] = current_settings

            # 3. 外観のみ更新（軽量な再描画）
            self._update_plot_appearance()

    def _update_subplot_combos(self):
            """
            「編集対象」「描画先」コンボボックスの中身（選択肢）を、
            現在の総プロット数に合わせて更新するヘルパーメソッドです。
            """
            total_plots = len(self.project.all_plot_settings)
            # (例: total_plots=2 の場合 -> ["プロット 1", "プロット 2"])
            plot_names = [f"プロット {i+1}" for i in range(total_plots)]

            # シグナルをブロック (clear/addItems/setCurrentIndex でシグナルが発火するのを防ぐ)
            self.active_axis_combo.blockSignals(True)
            self.subplot_target_combo.blockSignals(True)

            self.active_axis_combo.clear()
            self.subplot_target_combo.clear()

            self.active_axis_combo.addItems(plot_names)
            self.subplot_target_combo.addItems(plot_names)

            # 「編集対象」コンボボックスの選択状態を、現在のアクティブインデックスに合わせる
            self.active_axis_combo.setCurrentIndex(self.project.active_axis_index)

            # (「描画先」コンボボックスの選択状態は、_update_ui_state で
            #  データセットが選択されたときに設定される)

            self.active_axis_combo.blockSignals(False)
            self.subplot_target_combo.blockSignals(False)

    #==========================================================================
    # UI連動ヘルパーメソッド (スロット)
    #==========================================================================
    # これらのメソッドは、主に「あるUI (A)」の変更に応じて、
    # 「別のUI (B)」を有効化/無効化（グレーアウト）するために使われます。
    #
    # 【★ 注意 ★】
    # _connect_signals で、これらのメソッド（_on_grid_... 以外）への接続が
    # 漏れているため、現状では機能しません (上記【指摘】参照)。
    # #==========================================================================

    def _on_x_autoscale_changed(self):
        """X軸オートスケール チェックボックスが変更された"""
        is_autoscale = self.ui.x_autoscale_checkbox.isChecked()
        # オートスケールが ON なら、最小/最大スピンボックスを無効化
        self.ui.x_min_spinbox.setEnabled(not is_autoscale)
        self.ui.x_max_spinbox.setEnabled(not is_autoscale)

        # ★ ユーザーのコードのパターン (非効率だが意図を尊重)
        # 本来は _on_axis_setting_changed が呼ばれるので不要だが、
        # 元のコードの _on_grid_... に合わせて plot_appearance を呼ぶ
        self._update_plot_appearance()

    def _on_y_autoscale_changed(self):
        """Y軸オートスケール チェックボックスが変更された"""
        is_autoscale = self.ui.y_autoscale_checkbox.isChecked()
        # オートスケールが ON なら、最小/最大スピンボックスを無効化
        self.ui.y_min_spinbox.setEnabled(not is_autoscale)
        self.ui.y_max_spinbox.setEnabled(not is_autoscale)
        self._update_plot_appearance()

    def _on_x_tick_mode_changed(self):
        """X軸 主目盛モード (自動/固定) コンボボックスが変更された"""
        # currentIndex() == 1 が "固定間隔"
        is_fixed_interval = (self.ui.x_major_tick_mode_combo.currentIndex() == 1)
        # "固定間隔" が選ばれた場合のみ、間隔入力スピンボックスを有効化
        self.ui.x_major_tick_interval_spinbox.setEnabled(is_fixed_interval)
        self._update_plot_appearance()

    def _on_y_tick_mode_changed(self):
        """Y軸 主目盛モード (自動/固定) コンボボックスが変更された"""
        is_fixed_interval = (self.ui.y_major_tick_mode_combo.currentIndex() == 1)
        self.ui.y_major_tick_interval_spinbox.setEnabled(is_fixed_interval)
        self._update_plot_appearance()

    def _on_x_minor_tick_visibility_changed(self):
        """X軸 補助目盛表示 チェックボックスが変更された"""
        is_visible = self.ui.x_minor_ticks_visible_checkbox.isChecked()
        # チェックが ON の場合のみ、間隔入力スピンボックスを有効化
        self.ui.x_minor_tick_interval_spinbox.setEnabled(is_visible)
        self._update_plot_appearance()

    def _on_y_minor_tick_visibility_changed(self):
        """Y軸 補助目盛表示 チェックボックスが変更された"""
        is_visible = self.ui.y_minor_ticks_visible_checkbox.isChecked()
        self.ui.y_minor_tick_interval_spinbox.setEnabled(is_visible)
        self._update_plot_appearance()

    def _on_legend_visibility_changed(self):
        """
        凡例の表示/非表示チェックボックスが変更された。
        (★ 元のコードの _set_initial_ui_state には存在したが、
            PlotterApp のメソッドとしては定義されていなかったため追加)
        """
        is_visible = self.ui.legend_visible_checkbox.isChecked()

        # 凡例が非表示なら、位置、フォント、色の設定UIをすべて無効化
        self.legend_loc_label.setEnabled(is_visible)
        self.legend_loc_combo.setEnabled(is_visible)
        self.legend_font_label.setEnabled(is_visible)
        self.legend_font_button.setEnabled(is_visible)
        self.legend_color_label.setEnabled(is_visible)
        self.legend_color_button.setEnabled(is_visible)

        # (このメソッドも _connect_signals での接続が必要)
        # (self._update_plot_appearance() の呼び出しは _on_axis_setting_changed が
        #  担当するので、ここでは不要だが、ユーザーのパターンに合わせて追加)
        self._update_plot_appearance()


    def _grid_linestyle_code(self, combo_index: int) -> str:
        """グリッド線種コンボボックスの選択インデックスを、matplotlibのlinestyle文字列
        ('-' / '--' / ':' / '-.') に変換する (項目82)。"""
        choices = self.grid_linestyle_choices
        if 0 <= combo_index < len(choices):
            return choices[combo_index][1]
        return '-'

    def _grid_linestyle_index(self, linestyle_code: str) -> int:
        """matplotlibのlinestyle文字列を、グリッド線種コンボボックスの選択インデックスに
        逆変換する (項目82)。未知の値が来た場合は先頭(実線)を返す。"""
        for i, (_label, code) in enumerate(self.grid_linestyle_choices):
            if code == linestyle_code:
                return i
        return 0

    def _on_grid_visibility_changed(self):
        """
        メインのグリッド表示チェックボックスが変更されたときの処理
        (★ このメソッドは _connect_signals で正しく接続されています)
        """
        is_visible = self.ui.grid_visible_checkbox.isChecked()

        # 「補助グリッドも表示」チェックボックスの有効/無効を切り替え
        # (メイングリッドが OFF なら、補助グリッドも選択不可にする)
        self.ui.minor_grid_visible_checkbox.setEnabled(is_visible)

        # グリッド線の詳細カスタマイズ(項目82)コントロールの有効/無効も連動させる。
        # 主目盛用(線種/太さ/透過度)はメイングリッドのON/OFFに、
        # 補助目盛用はメイングリッド かつ 補助グリッド表示のON/OFFに従う。
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

    #==========================================================================
    # フォント・色 選択スロット
    #==========================================================================
    # これらは _connect_signals で ..._button.clicked に接続されています。
    #
    # パターン:
    # 1. ダイアログ (QFontDialog / QColorDialog) を開く
    # 2. ユーザーが "OK" を押したら (ok or color.isValid())
    # 3. 内部の状態変数 (self._tick_font など) を更新
    # 4. _on_axis_setting_changed() を呼び出し、変更を保存・適用する
    #==========================================================================

    def _on_change_tick_font(self):
        """「目盛フォント」ボタンが押された"""
        # (現在のフォント, 親ウィジェット) を渡す
        ok, font = QFontDialog.getFont(self._tick_font, self)
        if ok:
            self._tick_font = font
            self._on_axis_setting_changed() # 変更を保存・適用

    def _on_change_tick_color(self):
        """「目盛 文字色」ボタンが押された"""
        color = get_color_with_history(self.settings, self)
        if color.isValid():
            self._tick_color = color.name() # #RRGGBB 形式の文字列
            self._on_axis_setting_changed() # 変更を保存・適用

    def _on_change_axis_label_font(self):
        """「軸ラベルフォント」ボタンが押された"""
        ok, font = QFontDialog.getFont(self._axis_label_font, self)
        if ok:
            self._axis_label_font = font
            # 【★ バグ修正 ★】
            # _update_plot_appearance() ではなく _on_axis_setting_changed() を呼び出し、
            # 変更されたフォント設定 (self._axis_label_font) が
            # all_plot_settings に保存されるようにする。
            self._on_axis_setting_changed()

    def _on_change_axis_label_color(self):
        """「軸ラベル 文字色」ボタンが押された"""
        color = get_color_with_history(self.settings, self)
        if color.isValid():
            self._axis_label_color = color.name()
            # 【★ バグ修正 ★】 (上記と同様の理由)
            self._on_axis_setting_changed()

    def _on_change_legend_font(self):
        """「凡例フォント」ボタンが押された"""
        ok, font = QFontDialog.getFont(self._legend_font, self)
        if ok:
            self._legend_font = font
            self._on_axis_setting_changed() # 変更を保存・適用

    def _on_change_legend_color(self):
        """「凡例 文字色」ボタンが押された"""
        color = get_color_with_history(self.settings, self)
        if color.isValid():
            self._legend_color = color.name()
            self._on_axis_setting_changed() # 変更を保存・適用

    def _on_change_spine_color(self):
        """「外枠・目盛線 色」ボタンが押された"""
        color = get_color_with_history(self.settings, self)
        if color.isValid():
            self._spine_color = color.name()
            # 【★ バグ修正 ★】 (上記と同様の理由)
            self._on_axis_setting_changed()

    def _open_label_edit_dialog(self, line_edit, dialog_title):
        """
        タイトル/X軸ラベル/Y軸ラベルの「Aa」ボタンが押されたときの処理
        (実機フィードバックによるポップアップウィンドウ化、項目61/81/H-2-4)。
        LabelEditDialog(gui/dialogs.py)を開き、OKされたら結果をline_editへ
        書き戻す(setText()なのでtextChanged経由の_on_axis_setting_changedが
        通常通り発火し、既存の反映経路がそのまま使える)。

        ★ LABEL_SYMBOL_PALETTEはgui/main_window.py側の定義を、循環import
        (main_window.pyがこのMixinをインポートしているため)を避けるために
        ここで遅延importして渡している。
        """
        from gui.main_window import LABEL_SYMBOL_PALETTE

        dialog = LabelEditDialog(line_edit.text(), dialog_title, LABEL_SYMBOL_PALETTE, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            line_edit.setText(dialog.get_text())

    def _refresh_label_preview(self, preview_label, text, placeholder):
        """
        タイトル/X軸ラベル/Y軸ラベルのプレビューラベル(_ClickableMathPreviewLabel、
        gui/main_window.py)の表示を、現在のテキストを実際にmatplotlibで
        レンダリングした見た目に更新する(項目H-2-4追加分、実機フィードバック:
        「mathtextを翻訳した形式をプレビューしといて」)。テキストが空の場合は
        placeholderをtext_muted色で表示する(QLineEditのplaceholderTextと
        同じ役割)。line_edit.textChanged、および初期表示・ダークモード切り替え
        (_refresh_all_label_previews)から呼ばれる。
        """
        from gui.mathtext_preview import render_mathtext_to_pixmap

        tokens = theme.current_tokens()
        if text:
            pixmap = render_mathtext_to_pixmap(text, color=tokens["text_primary"])
        else:
            pixmap = render_mathtext_to_pixmap(placeholder, color=tokens["text_muted"])
        # ★ 実機フィードバック: 「ここの文字サイズを枠内に収まるようにして」
        #   (長いmathtext文字列がプレビュー欄の枠からはみ出していた)。
        #   set_natural_pixmap()は「等倍」のpixmapを保持しておき、ウィジェット
        #   自身の実際の幅が確定するたび(resizeEvent、タブ切り替え・
        #   ウィンドウリサイズ等を含む)自動的に収まるよう再フィットする
        #   (単純なsetPixmap()だと、この呼び出し時点でのwidth()が
        #   まだ実際のレイアウト確定値と一致しない場合にはみ出したままに
        #   なる、FitWidthPixmapLabel参照)。
        preview_label.set_natural_pixmap(pixmap)

    def _refresh_all_label_previews(self):
        """
        ダークモード切り替え時に、タイトル/X軸ラベル/Y軸ラベルの全プレビューを
        再レンダリングする(文字色がtext_primary/text_mutedトークン経由で
        テーマに追従しているため、テーマが変わったら再描画しないと古い配色の
        まま残ってしまう)。
        """
        for preview_label, line_edit, placeholder in self._label_preview_widgets:
            self._refresh_label_preview(preview_label, line_edit.text(), placeholder)

    def _on_edit_legend_order(self):
        """
        「凡例の順序...」ボタンが押されたときの処理。
        現在アクティブな軸に描画されているデータセットの凡例ラベルを、
        (保存済みのカスタム順があればそれを初期値として) ドラッグで並べ替えられる
        ダイアログを表示し、結果を軸ごとの設定 (legend_order) に保存する。
        """
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

        current_order = self.project.all_plot_settings[axis_index].get('legend_order') or []
        dialog = LegendOrderDialog(_order_labels(labels, current_order), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.project.all_plot_settings[axis_index]['legend_order'] = dialog.get_order()
        self._update_plot()

    #==========================================================================
    # 【★ 指摘: 以下のメソッドは「デッドコード」 ★】
    # _connect_signals で valueChanged シグナルは _on_axis_setting_changed に
    # 接続されているため、これらのスロットは実際には呼び出されません。
    #==========================================================================

    def _on_tick_width_changed(self, value):
        """(呼び出されない) 目盛の太さ スピンボックスが変更された"""
        self._tick_width = value
        self._update_plot_appearance()

    def _on_spine_width_changed(self, value):
        """(呼び出されない) 外枠の太さ スピンボックスが変更された"""
        self._spine_width = value
        self._update_plot_appearance()

    def _font_props_to_dict(self, qfont: QFont) -> dict:
        """
        PySide6のQFontオブジェクトをMatplotlib用の（JSON保存可能な）辞書に変換する。
        (★ __init__ でインポートした FontProperties ではないことに注意)

        ★ 'family'は単一の名前(str)ではなく、qfont.families()が返す
        フォールバック候補リストをそのまま保存する。既定フォント
        (gui/main_window.py の _make_default_plot_font())はWindows/macOS
        双方の日本語フォント名を含むフォールバックリストで構築されているため、
        ここを.family()(先頭の1件しか返さない)にすると、matplotlib側に
        渡すリストが1件に潰れてしまい、macOSでは存在しない"Yu Gothic"だけが
        残って日本語が文字化けする。matplotlibのfamilyキーワードはstr/list
        どちらも受け付けるため、ユーザーがQFontDialogで単一フォントを選んだ
        場合(families()が1件のリストを返す)も含めて、常にリストとして保存する。
        """
        return {
            'family': list(qfont.families()),
            'size': qfont.pointSize(),
            'weight': 'bold' if qfont.bold() else 'normal',
            'style': 'italic' if qfont.italic() else 'normal'
        }

    def _gather_settings_from_ui(self) -> dict:
        """
        現在のUIコントロール（スピンボックス、テキスト、内部変数）の状態を
        「すべて」収集し、1つの辞書として返します。

        Returns:
            dict: 現在のUI設定のスナップショット。
        """
        settings = {
            # ラベル/書式タブ
            'title': self.ui.title_text_edit.text(),
            'x_label': self.ui.x_label_text_edit.text(),
            'y_label': self.ui.y_label_text_edit.text(),
            'y2_label': self.y2_label_text_edit.text(),

            # X軸タブ
            'x_autoscale': self.ui.x_autoscale_checkbox.isChecked(),
            'x_min': self.ui.x_min_spinbox.value(),
            'x_max': self.ui.x_max_spinbox.value(),
            'x_log': self.ui.x_log_checkbox.isChecked(),
            'x_invert': self.ui.x_invert_checkbox.isChecked(),
            'x_major_tick_mode': self.ui.x_major_tick_mode_combo.currentIndex(),
            'x_major_tick_interval': self.ui.x_major_tick_interval_spinbox.value(),
            'x_minor_ticks_visible': self.ui.x_minor_ticks_visible_checkbox.isChecked(),
            'x_minor_tick_interval': self.ui.x_minor_tick_interval_spinbox.value(),
            'x_tick_format_mode': self.x_tick_format_combo.currentIndex(),
            'x_secondary_axis_source_unit':
                X_AXIS_UNIT_CHOICES[self.x_secondary_axis_source_unit_combo.currentIndex()],
            'x_secondary_axis_target_unit':
                X_AXIS_UNIT_CHOICES[self.x_secondary_axis_target_unit_combo.currentIndex()],

            # Y軸タブ
            'y_autoscale': self.ui.y_autoscale_checkbox.isChecked(),
            'y_min': self.ui.y_min_spinbox.value(),
            'y_max': self.ui.y_max_spinbox.value(),
            'y_log': self.ui.y_log_checkbox.isChecked(),
            'y_invert': self.ui.y_invert_checkbox.isChecked(),
            'y_major_tick_mode': self.ui.y_major_tick_mode_combo.currentIndex(),
            'y_major_tick_interval': self.ui.y_major_tick_interval_spinbox.value(),
            'y_minor_ticks_visible': self.ui.y_minor_ticks_visible_checkbox.isChecked(),
            'y_minor_tick_interval': self.ui.y_minor_tick_interval_spinbox.value(),
            'y_tick_format_mode': self.y_tick_format_combo.currentIndex(),

            # ラベル/書式タブ (続き)
            'legend_visible': self.ui.legend_visible_checkbox.isChecked(),
            'legend_loc': self.legend_loc_combo.currentText(),
            'grid_visible': self.ui.grid_visible_checkbox.isChecked(),
            'minor_grid_visible': self.ui.minor_grid_visible_checkbox.isChecked(),

            # グリッド線の詳細カスタマイズ(項目82): X/Y軸 × 主/補助目盛 それぞれ独立
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

            # 内部の (self._...) 変数
            'tick_font': self._font_props_to_dict(self._tick_font),
            'tick_color': self._tick_color,
            'tick_width': self.ui.tick_width_spinbox.value(),
            'axis_label_font': self._font_props_to_dict(self._axis_label_font),
            'axis_label_color': self._axis_label_color,
            'legend_font': self._font_props_to_dict(self._legend_font),
            'legend_color': self._legend_color,
            'spine_width': self.ui.spine_width_spinbox.value(),
            'spine_color': self._spine_color,
        }

        # ★ 注釈(テキスト・矢印)はUIコントロールを持たず、_add_annotation等から
        # 直接 all_plot_settings[index]['annotations'] へ追記される。
        # このメソッドは呼ばれるたびに辞書を「総入れ替え」するため、ここで
        # 明示的に引き継がないと、他の軸設定を変更しただけで注釈が消えてしまう。
        # ★ 自由配置レイアウト(項目37)の各サブプロットの矩形(free_rect)も同様に、
        # UIコントロールを持たずドラッグ操作から直接書き込まれるため、ここで引き継ぐ。
        if self.project.active_axis_index < len(self.project.all_plot_settings):
            current = self.project.all_plot_settings[self.project.active_axis_index]
            settings['annotations'] = current.get('annotations', [])
            settings['legend_order'] = current.get('legend_order', [])
            settings['free_rect'] = current.get('free_rect')
        else:
            settings['annotations'] = []
            settings['legend_order'] = []
            settings['free_rect'] = None
        return settings

    def _apply_settings_to_ui_controls(self, settings: dict):
        """
        settings 辞書を受け取り、その内容をUIコントロール
        (スピンボックス、チェックボックス、内部変数など) に「適用」します。

        Args:
            settings (dict): _gather_settings_from_ui() で作成された形式の辞書。
        """
        try:
            # 1. ★★★ 必須 ★★★
            #    これからUIの値をコードで一括変更するため、
            #    シグナルが発火しないようにすべてブロックする
            self._block_all_signals(True)

            # 2. settings 辞書から値を取得し、UIにセット
            #    .get(key, default) を使い、キーが存在しなくてもエラーにならないようにする

            # ラベル/書式
            self.ui.title_text_edit.setText(settings.get('title', ''))
            self.ui.x_label_text_edit.setText(settings.get('x_label', ''))
            self.ui.y_label_text_edit.setText(settings.get('y_label', ''))
            self.y2_label_text_edit.setText(settings.get('y2_label', ''))

            # X軸
            self.ui.x_autoscale_checkbox.setChecked(settings.get('x_autoscale', True))
            self.ui.x_min_spinbox.setValue(settings.get('x_min', 0))
            self.ui.x_max_spinbox.setValue(settings.get('x_max', 1))
            self.ui.x_log_checkbox.setChecked(settings.get('x_log', False))
            self.ui.x_invert_checkbox.setChecked(settings.get('x_invert', False))
            self.ui.x_major_tick_mode_combo.setCurrentIndex(settings.get('x_major_tick_mode', 0))
            self.ui.x_major_tick_interval_spinbox.setValue(settings.get('x_major_tick_interval', 1))
            self.ui.x_minor_ticks_visible_checkbox.setChecked(settings.get('x_minor_ticks_visible', False))
            self.ui.x_minor_tick_interval_spinbox.setValue(settings.get('x_minor_tick_interval', 0.5))
            self.x_tick_format_combo.setCurrentIndex(settings.get('x_tick_format_mode', 0))
            _source_unit = settings.get('x_secondary_axis_source_unit', X_AXIS_UNIT_NONE)
            self.x_secondary_axis_source_unit_combo.setCurrentIndex(
                X_AXIS_UNIT_CHOICES.index(_source_unit) if _source_unit in X_AXIS_UNIT_CHOICES else 0)
            _target_unit = settings.get('x_secondary_axis_target_unit', X_AXIS_UNIT_NONE)
            self.x_secondary_axis_target_unit_combo.setCurrentIndex(
                X_AXIS_UNIT_CHOICES.index(_target_unit) if _target_unit in X_AXIS_UNIT_CHOICES else 0)

            # Y軸
            self.ui.y_autoscale_checkbox.setChecked(settings.get('y_autoscale', True))
            self.ui.y_min_spinbox.setValue(settings.get('y_min', 0))
            self.ui.y_max_spinbox.setValue(settings.get('y_max', 1))
            self.ui.y_log_checkbox.setChecked(settings.get('y_log', False))
            self.ui.y_invert_checkbox.setChecked(settings.get('y_invert', False))
            self.ui.y_major_tick_mode_combo.setCurrentIndex(settings.get('y_major_tick_mode', 0))
            self.ui.y_major_tick_interval_spinbox.setValue(settings.get('y_major_tick_interval', 1))
            self.ui.y_minor_ticks_visible_checkbox.setChecked(settings.get('y_minor_ticks_visible', False))
            self.ui.y_minor_tick_interval_spinbox.setValue(settings.get('y_minor_tick_interval', 0.5))
            self.y_tick_format_combo.setCurrentIndex(settings.get('y_tick_format_mode', 0))

            # ラベル/書式 (続き)
            self.ui.legend_visible_checkbox.setChecked(settings.get('legend_visible', True))
            self.legend_loc_combo.setCurrentText(settings.get('legend_loc', 'best'))
            self.ui.grid_visible_checkbox.setChecked(settings.get('grid_visible', False))
            self.ui.minor_grid_visible_checkbox.setChecked(settings.get('minor_grid_visible', False))

            # グリッド線の詳細カスタマイズ(項目82)。旧プロジェクト(このキー群が
            # 存在しない)を読み込んだ場合は、canvas.py 側と同じデフォルト値
            # (主目盛: 実線・太さ0.8 / 補助目盛: 破線・太さ0.5、共にalpha=1.0)にする。
            self.x_major_grid_linestyle_combo.setCurrentIndex(
                self._grid_linestyle_index(settings.get('x_major_grid_linestyle', '-')))
            self.x_major_grid_width_spinbox.setValue(settings.get('x_major_grid_width', 0.8))
            self.x_major_grid_alpha_spinbox.setValue(settings.get('x_major_grid_alpha', 1.0))
            self.x_minor_grid_linestyle_combo.setCurrentIndex(
                self._grid_linestyle_index(settings.get('x_minor_grid_linestyle', '--')))
            self.x_minor_grid_width_spinbox.setValue(settings.get('x_minor_grid_width', 0.5))
            self.x_minor_grid_alpha_spinbox.setValue(settings.get('x_minor_grid_alpha', 1.0))
            self.y_major_grid_linestyle_combo.setCurrentIndex(
                self._grid_linestyle_index(settings.get('y_major_grid_linestyle', '-')))
            self.y_major_grid_width_spinbox.setValue(settings.get('y_major_grid_width', 0.8))
            self.y_major_grid_alpha_spinbox.setValue(settings.get('y_major_grid_alpha', 1.0))
            self.y_minor_grid_linestyle_combo.setCurrentIndex(
                self._grid_linestyle_index(settings.get('y_minor_grid_linestyle', '--')))
            self.y_minor_grid_width_spinbox.setValue(settings.get('y_minor_grid_width', 0.5))
            self.y_minor_grid_alpha_spinbox.setValue(settings.get('y_minor_grid_alpha', 1.0))
            self.major_tick_direction_combo.setCurrentText(settings.get('major_tick_direction', 'out'))
            self.minor_tick_direction_combo.setCurrentText(settings.get('minor_tick_direction', 'out'))
            self.major_tick_direction_y2_combo.setCurrentText(settings.get('major_tick_direction_y2', 'out'))
            self.minor_tick_direction_y2_combo.setCurrentText(settings.get('minor_tick_direction_y2', 'out'))

            # 3. 内部の (self._...) 変数を辞書から復元

            # (フォントの復元)
            tick_font_props = settings.get('tick_font', {})
            self._tick_font = _qfont_from_family_props(tick_font_props)
            self._tick_font.setPointSize(tick_font_props.get('size', 10))
            self._tick_font.setBold(tick_font_props.get('weight') == 'bold')
            self._tick_font.setItalic(tick_font_props.get('style') == 'italic')

            label_font_props = settings.get('axis_label_font', {})
            self._axis_label_font = _qfont_from_family_props(label_font_props)
            self._axis_label_font.setPointSize(label_font_props.get('size', 10))
            self._axis_label_font.setBold(label_font_props.get('weight') == 'bold')
            self._axis_label_font.setItalic(label_font_props.get('style') == 'italic')

            legend_font_props = settings.get('legend_font', {})
            self._legend_font = _qfont_from_family_props(legend_font_props)
            if 'size' in legend_font_props:
                self._legend_font.setPointSize(legend_font_props.get('size', 10))
            self._legend_font.setBold(legend_font_props.get('weight') == 'bold')
            self._legend_font.setItalic(legend_font_props.get('style') == 'italic')

            # (色と太さの復元)
            self._tick_color = settings.get('tick_color', '#000000')
            self._tick_width = settings.get('tick_width', 0.8)
            self.ui.tick_width_spinbox.setValue(self._tick_width) # ★ UIにも反映

            self._axis_label_color = settings.get('axis_label_color', '#000000')
            self._legend_color = settings.get('legend_color', '#000000')

            self._spine_width = settings.get('spine_width', 1.0)
            self.ui.spine_width_spinbox.setValue(self._spine_width) # ★ UIにも反映
            self._spine_color = settings.get('spine_color', '#000000')

            # 4. UIの状態を更新 (スピンボックスの有効/無効など)
            #    (★ _connect_signals での接続修正が前提)
            self._on_x_autoscale_changed()
            self._on_y_autoscale_changed()
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
            # 5. ★★★ 必須 ★★★
            #    成功しても失敗しても、シグナルを必ず元に戻す
            self._block_all_signals(False)

    def _block_all_signals(self, block: bool):
        """
        UIコントロールのシグナルを一括でブロック(True) / 解除(False) する
        ヘルパーメソッド。_apply_settings_to_ui_controls で使用。
        """
        # X軸タブ
        self.ui.x_autoscale_checkbox.blockSignals(block)
        self.ui.x_min_spinbox.blockSignals(block)
        self.ui.x_max_spinbox.blockSignals(block)
        self.ui.x_log_checkbox.blockSignals(block)
        self.ui.x_invert_checkbox.blockSignals(block)
        self.ui.x_major_tick_mode_combo.blockSignals(block)
        self.ui.x_major_tick_interval_spinbox.blockSignals(block)
        self.ui.x_minor_ticks_visible_checkbox.blockSignals(block)
        self.ui.x_minor_tick_interval_spinbox.blockSignals(block)
        self.x_tick_format_combo.blockSignals(block)
        self.x_secondary_axis_source_unit_combo.blockSignals(block)
        self.x_secondary_axis_target_unit_combo.blockSignals(block)

        # Y軸タブ
        self.ui.y_autoscale_checkbox.blockSignals(block)
        self.ui.y_min_spinbox.blockSignals(block)
        self.ui.y_max_spinbox.blockSignals(block)
        self.ui.y_log_checkbox.blockSignals(block)
        self.ui.y_invert_checkbox.blockSignals(block)
        self.ui.y_major_tick_mode_combo.blockSignals(block)
        self.ui.y_major_tick_interval_spinbox.blockSignals(block)
        self.ui.y_minor_ticks_visible_checkbox.blockSignals(block)
        self.ui.y_minor_tick_interval_spinbox.blockSignals(block)
        self.y_tick_format_combo.blockSignals(block)

        # ラベル/書式タブ
        self.ui.title_text_edit.blockSignals(block)
        self.ui.x_label_text_edit.blockSignals(block)
        self.ui.y_label_text_edit.blockSignals(block)
        self.y2_label_text_edit.blockSignals(block)
        self.ui.tick_font_button.blockSignals(block)
        self.ui.tick_color_button.blockSignals(block)
        self.ui.tick_width_spinbox.blockSignals(block)
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
