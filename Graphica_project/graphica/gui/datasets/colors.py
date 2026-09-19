"""データセットの色: 色の変更、自動配色、名前付きの色の適用、配色パレットの管理。"""
import json
import logging
import matplotlib as mpl
from PySide6.QtWidgets import (QDialog, QInputDialog)

from graphica.core.color_palettes import BUILTIN_PALETTES
from graphica.core.named_colors import POPUP_LIMIT, load_named_colors
from graphica.gui.dialogs import (ColorPaletteDialog)

logger = logging.getLogger(__name__)

# カスタム配色パレットをQSettingsに保存する際のキー
COLOR_PALETTES_SETTINGS_KEY = "custom_color_palettes_json"
ACTIVE_PALETTE_SETTINGS_KEY = "active_color_palette"

# エラーバー用の誤差列コンボボックスで「誤差列を使わない」ことを表す選択肢
NO_ERROR_COLUMN_LABEL = "(なし)"

# 「スタイルのコピー&ペースト」で複製対象とする、見た目に関する属性
# (凡例名・X/Y列・エラーバー列・描画先など、データ/構造に関わるものは含めない)。
# colormap/vmin/vmax/grid_interp_methodは2Dマップ(項目C-508)の見た目に関する
# 属性のため含めるが、data_kind/z_col_nameはX/Y列と同様に「どの列を使うか」という
# 構造の選択であり、他のデータセットへ無条件にコピーすると意図しない相手を
# 2Dグリッド扱いにしてしまうため、意図的に含めない。
STYLE_ATTRS = ('plot_type', 'color', 'linestyle', 'linewidth', 'marker', 'markersize', 'smoothing',
               'smoothing_method', 'alpha',
               'error_display', 'colormap', 'vmin', 'vmax', 'grid_interp_method')

# カラーマップからの自動配色(項目C-805)で選ばせる候補。連続データの系列を
# 表現するのに適した(知覚的に均一な、またはよく使われる)ものを厳選する。
RECOMMENDED_COLORMAPS = ['viridis', 'plasma', 'cividis', 'coolwarm', 'turbo', 'rainbow']

# データポイントラベルの「内容」コンボボックスで、Y値そのものを表示することを示す選択肢
POINT_LABEL_Y_VALUE_LABEL = "Y値"


class ColorController:
    """データセットの色と配色パレット。"""

    def __init__(self, host):
        self._host = host

    def on_color_changed(self, new_color):
        """
        データセットの色選択ウィジェット (color_picker_widget、項目65) で
        色が変更されたときの処理。スウォッチのパレット展開・カラーコード欄への
        直接入力のどちらの経路でも呼ばれる (色選択・表示更新自体はウィジェット側で
        完結済みのため、ここでは選ばれた色をDatasetに適用するだけでよい)。
        複数のデータセットが選択されている場合は、全てに同じ色を適用し、
        1回のUndo/Redoでまとめて元に戻せるようにする。
        """
        selected_datasets = self._host.selected_datasets()
        if not selected_datasets:
            return

        # Undo/Redo可能なコマンドとして発行
        #    複数選択時は beginMacro/endMacro で1つの操作としてまとめる
        is_batch = len(selected_datasets) > 1
        if is_batch:
            self._host.undo_stack.beginMacro(f"データセットの色を一括変更 ({len(selected_datasets)}件)")
        for dataset in selected_datasets:
            self._host.push_property_change(
                dataset,
                {'color': dataset.color},
                {'color': new_color},
                description="データセットの色変更"
            )
        if is_batch:
            self._host.undo_stack.endMacro()

    def on_gradient_color2_changed(self, new_color):
        """
        グラデーション終端色ウィジェット (gradient_color2_picker、項目79) で
        色が変更されたときの処理。_on_dataset_color_changed (開始色=color) と
        同様のUndo/Redo・複数選択一括適用パターンを、gradient_color2に対して行う。
        """
        selected_datasets = self._host.selected_datasets()
        if not selected_datasets:
            return

        is_batch = len(selected_datasets) > 1
        if is_batch:
            self._host.undo_stack.beginMacro(f"グラデーション終端色を一括変更 ({len(selected_datasets)}件)")
        for dataset in selected_datasets:
            self._host.push_property_change(
                dataset,
                {'gradient_color2': dataset.gradient_color2},
                {'gradient_color2': new_color},
                description="グラデーション終端色の変更"
            )
        if is_batch:
            self._host.undo_stack.endMacro()

    def auto_assign_colors(self):
        """
        「自動配色」ボタンが押されたときの処理。
        選択中の(複数可)データセットに、現在アクティブなカラーパレット
        (ユーザーが「パレット管理」で作成したもの、または既定のmatplotlibの
        カラーサイクル) を順番に自動で割り当てる。
        手動で1つずつ色を選ぶ手間を省くための一括操作。
        """
        selected_datasets = self._host.selected_datasets()
        if not selected_datasets:
            return

        color_cycle = self._host.active_color_cycle()

        is_batch = len(selected_datasets) > 1
        if is_batch:
            self._host.undo_stack.beginMacro(f"配色の自動割り当て ({len(selected_datasets)}件)")
        for i, dataset in enumerate(selected_datasets):
            new_color = color_cycle[i % len(color_cycle)]
            self._host.push_property_change(
                dataset,
                {'color': dataset.color},
                {'color': new_color},
                description="配色の自動割り当て"
            )
        if is_batch:
            self._host.undo_stack.endMacro()

    def populate_named_color_menu(self):
        """
        オーバーフローメニューの「登録した色を適用 ▶」の中身を詰め直す。

        登録内容は「色名の管理」でいつでも変わるので、開くたびに作り直す
        (データセットメニューと同じ方式)。1件も登録が無いときは、無効化した
        案内項目を1つだけ出す — 空のサブメニューを開いて何も無いより、
        「どこで登録するのか」が分かる方が親切なため。
        """
        menu = getattr(self._host.parent_widget, '_named_color_apply_menu', None)
        if menu is None:
            return
        menu.clear()
        entries = load_named_colors(self._host.settings)
        if not entries:
            empty_action = menu.addAction("(登録がありません)")
            empty_action.setEnabled(False)
            return
        # 色欄のポップアップと同じく、並べるのは先頭 POPUP_LIMIT 件まで。
        for entry in entries[:POPUP_LIMIT]:
            action = menu.addAction(
                _named_color_menu_icon(entry["color"]),
                f'{entry["name"]}	{entry["color"]}')
            action.triggered.connect(
                lambda checked=False, c=entry["color"], n=entry["name"]:
                    self.apply_named_color_to_selection(c, n))
        if len(entries) > POPUP_LIMIT:
            more_action = menu.addAction(f"すべての登録色... ({len(entries)}件)")
            more_action.triggered.connect(self.apply_named_color_from_list)

    def apply_named_color_from_list(self):
        """登録が POPUP_LIMIT 件を超えたときに、検索欄付きの一覧から選んで適用する。"""
        from graphica.gui.dialogs import NamedColorPickerDialog
        dialog = NamedColorPickerDialog(self._host.settings, self._host.parent_widget, title="登録色を適用")
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        entry = dialog.selected_entry()
        if entry:
            self.apply_named_color_to_selection(entry["color"], entry["name"])

    def apply_named_color_to_selection(self, color, name):
        """
        登録した色を、選択中の(複数可)データセットへまとめて適用する。
        N件の変更が Undo 1回で戻るのは「自動配色」と同じ
        (_on_auto_assign_colors と同じ beginMacro の型)。
        """
        selected_datasets = self._host.selected_datasets()
        if not selected_datasets:
            self._host.show_status("データセットを選択してください。", 4000)
            return

        # ★ 既にその色のものを先に除く。空のままbeginMacro/endMacroすると、
        #   Qtは「中身ゼロのマクロ」をそのままスタックへ積むため、何も変わって
        #   いないのにUndoが1回分増える(押しても何も起きないUndoができてしまう)。
        targets = [ds for ds in selected_datasets if ds.color != color]
        if not targets:
            self._host.show_status(f"選択中のデータセットは既に「{name}」の色です。", 4000)
            return

        is_batch = len(targets) > 1
        if is_batch:
            self._host.undo_stack.beginMacro(f"「{name}」の色を適用 ({len(targets)}件)")
        for dataset in targets:
            self._host.push_property_change(
                dataset,
                {'color': dataset.color},
                {'color': color},
                description=f"「{name}」の色を適用",
            )
        if is_batch:
            self._host.undo_stack.endMacro()

    def auto_assign_colors_from_colormap(self):
        """
        「カラーマップから自動配色...」メニューの処理(項目C-805)。
        _on_auto_assign_colors が離散パレットを順番に割り当てるのに対し、
        こちらは連続カラーマップ(viridis等)から選択中のデータセット数ぶんを
        均等サンプリングして割り当てる。時系列/濃度変化など、順序に意味のある
        系列をグラデーションで表現したい場合向け。
        """
        selected_datasets = self._host.selected_datasets()
        if not selected_datasets:
            return

        cmap_name, ok = QInputDialog.getItem(
            self._host.parent_widget, "カラーマップから自動配色", "使用するカラーマップを選択してください:",
            RECOMMENDED_COLORMAPS, 0, False
        )
        if not ok:
            return

        cmap = mpl.colormaps[cmap_name]
        n = len(selected_datasets)
        # n==1のときの0除算を避ける(1件ならカラーマップの中央値を使う)
        positions = [0.5] if n == 1 else [i / (n - 1) for i in range(n)]
        new_colors = [mpl.colors.to_hex(cmap(p)) for p in positions]

        is_batch = n > 1
        if is_batch:
            self._host.undo_stack.beginMacro(f"カラーマップからの配色 ({n}件)")
        for dataset, new_color in zip(selected_datasets, new_colors):
            self._host.push_property_change(
                dataset, {'color': dataset.color}, {'color': new_color},
                description="カラーマップからの配色"
            )
        if is_batch:
            self._host.undo_stack.endMacro()

    def load_palettes(self):
        """QSettingsに保存されているカスタム配色パレット一式を辞書として読み込む"""
        raw = self._host.settings.value(COLOR_PALETTES_SETTINGS_KEY, "")
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("カスタム配色パレットの読み込みに失敗しました。空として扱います。")
            return {}

    def save_palettes(self, palettes: dict):
        """カスタム配色パレット一式をQSettingsに保存する"""
        self._host.settings.setValue(COLOR_PALETTES_SETTINGS_KEY, json.dumps(palettes))

    def active_color_cycle(self):
        """
        現在アクティブなパレットの色リストを返す。
        パレットが未設定、または空の場合はmatplotlibの既定カラーサイクルにフォールバックする。
        組み込みの論文向けパレット(項目141、C-804、BUILTIN_PALETTES)も
        ユーザーのカスタムパレットと同じ扱いで名前解決する。
        """
        active_name = self._host.settings.value(ACTIVE_PALETTE_SETTINGS_KEY, ColorPaletteDialog.DEFAULT_PALETTE_NAME)
        if active_name in BUILTIN_PALETTES:
            return BUILTIN_PALETTES[active_name]
        palettes = self.load_palettes()
        if active_name != ColorPaletteDialog.DEFAULT_PALETTE_NAME and palettes.get(active_name):
            return palettes[active_name]
        return mpl.rcParams['axes.prop_cycle'].by_key()['color']

    def manage_palettes(self):
        """「パレット管理...」ボタンが押されたときの処理。ダイアログで編集後、設定に保存する。"""
        palettes = self.load_palettes()
        active_name = self._host.settings.value(ACTIVE_PALETTE_SETTINGS_KEY, ColorPaletteDialog.DEFAULT_PALETTE_NAME)

        dialog = ColorPaletteDialog(palettes, active_name, self._host.parent_widget)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_palettes, new_active_name = dialog.get_result()
            self.save_palettes(new_palettes)
            self._host.settings.setValue(ACTIVE_PALETTE_SETTINGS_KEY, new_active_name)


def _named_color_menu_icon(color_name, size=16):
    """「登録した色を適用」メニューの色見本(色欄のポップアップと同じ描き方)。"""
    from graphica.gui.color_picker_widget import _color_icon
    return _color_icon(color_name, size=size)
