"""データセットの色: 色の変更、自動配色、名前付きの色の適用、配色パレットの管理。"""
import json
import logging
import matplotlib as mpl
from PySide6.QtWidgets import (QDialog)

from graphica.gui import notify
from graphica.core.color_palettes import BUILTIN_PALETTES
from graphica.core.named_colors import POPUP_LIMIT, load_named_colors
from graphica.gui import app_settings
from graphica.gui.dialogs import (ColorPaletteDialog)

logger = logging.getLogger(__name__)


# カラーマップからの自動配色で選ばせる候補(順序のある系列に向く、知覚的に均一なもの中心)。
RECOMMENDED_COLORMAPS = ['viridis', 'plasma', 'cividis', 'coolwarm', 'turbo', 'rainbow']


class ColorController:
    """データセットの色と配色パレット。"""

    def __init__(self, host):
        self._host = host

    def on_color_changed(self, new_color):
        """色欄で選んだ色を選択中のデータセットすべてに当てる(Undo 1回分)。"""
        selected_datasets = self._host.selected_datasets()
        if not selected_datasets:
            return

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
        """グラデーションの終端色を選択中のデータセットすべてに当てる(Undo 1回分)。"""
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
        """選択中のデータセットに、今のパレットの色を順に割り当てる。"""
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
        「登録した色を適用」の中身を作り直す(登録はいつでも変わるので開くたびに)。
        登録が無いときは、空のメニューではなく無効な案内項目を1つ出す。
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
        """登録した色を選択中のデータセットに当てる(Undo 1回分)。"""
        selected_datasets = self._host.selected_datasets()
        if not selected_datasets:
            self._host.show_status("データセットを選択してください。", 4000)
            return

        # 変わらないものを先に除く。空のマクロでも Qt は Undo を1回分積んでしまう。
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
        """選択中のデータセットに、カラーマップから等間隔に取った色を割り当てる(順序のある系列向け)。"""
        selected_datasets = self._host.selected_datasets()
        if not selected_datasets:
            return

        cmap_name, ok = notify.get_item(
            self._host.parent_widget, "カラーマップから自動配色", "使用するカラーマップを選択してください:",
            RECOMMENDED_COLORMAPS, 0, False
        )
        if not ok:
            return

        cmap = mpl.colormaps[cmap_name]
        n = len(selected_datasets)
        # 1件ならカラーマップの中央の色
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
        raw = app_settings.CUSTOM_COLOR_PALETTES.read(self._host.settings)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("カスタム配色パレットの読み込みに失敗しました。空として扱います。")
            return {}

    def save_palettes(self, palettes: dict):
        app_settings.CUSTOM_COLOR_PALETTES.write(self._host.settings, json.dumps(palettes))

    def active_color_cycle(self):
        """今のパレットの色。未設定や空なら matplotlib の既定の色の並び。"""
        active_name = app_settings.ACTIVE_COLOR_PALETTE.read(
            self._host.settings, default=ColorPaletteDialog.DEFAULT_PALETTE_NAME)
        if active_name in BUILTIN_PALETTES:
            return BUILTIN_PALETTES[active_name]
        palettes = self.load_palettes()
        if active_name != ColorPaletteDialog.DEFAULT_PALETTE_NAME and palettes.get(active_name):
            return palettes[active_name]
        return mpl.rcParams['axes.prop_cycle'].by_key()['color']

    def manage_palettes(self):
        palettes = self.load_palettes()
        active_name = app_settings.ACTIVE_COLOR_PALETTE.read(
            self._host.settings, default=ColorPaletteDialog.DEFAULT_PALETTE_NAME)

        dialog = ColorPaletteDialog(palettes, active_name, self._host.parent_widget)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_palettes, new_active_name = dialog.get_result()
            self.save_palettes(new_palettes)
            app_settings.ACTIVE_COLOR_PALETTE.write(self._host.settings, new_active_name)


def _named_color_menu_icon(color_name, size=16):
    """「登録した色を適用」メニューの色見本(色欄のポップアップと同じ描き方)。"""
    from graphica.gui.color_picker_widget import _color_icon
    return _color_icon(color_name, size=size)
