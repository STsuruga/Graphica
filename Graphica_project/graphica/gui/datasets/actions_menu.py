"""データセット操作メニュー(ツリーの右クリックとツールバーのボタンで同じものを出す)。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMenu


def populate_dataset_actions_menu(app, menu):
    """
    app(1つのタブ)の今の選択に合わせて menu の中身を作り直す。

    選択に応じて出し入れする項目があるので、開くたびに作り直す。PySide6 が途中で
    サブメニューを回収しないよう、Python 側の参照はメニュー自身に持たせる(_graphica_submenus)。
    """
    menu.clear()
    submenus = []

    def add_submenu(title):
        """空のまま出さないよう、項目が入ったものだけ最後に menu へ繋ぐ。"""
        sub = QMenu(title, menu)
        submenus.append(sub)
        return sub

    data_proc_menu = add_submenu("データ処理")
    analysis_menu = add_submenu("解析・注釈")
    multi_menu = add_submenu("複数データセット")
    export_menu = add_submenu("エクスポート")
    tab_menu = add_submenu("タブ操作")

    menu.addAction("新しいフォルダ").triggered.connect(app._on_new_folder)
    if app.project.datasets:
        menu.addAction("すべて表示").triggered.connect(app._on_show_all_datasets)
        menu.addAction("すべて非表示").triggered.connect(app._on_hide_all_datasets)

    current_item = app.ui.dataset_list_widget.currentItem()
    if current_item is not None and current_item.data(0, Qt.ItemDataRole.UserRole) is None:
        menu.addAction("フォルダ名を変更...").triggered.connect(app._on_rename_dataset_folder)
        menu.addAction("フォルダ内を全て表示").triggered.connect(app._on_show_all_in_folder)
        menu.addAction("フォルダ内を全て非表示").triggered.connect(app._on_hide_all_in_folder)

    current = app._get_current_dataset()
    if current is not None:
        menu.addSeparator()
        menu.addAction("スタイルをコピー").triggered.connect(app.transfer.copy_style)
        paste_style_action = menu.addAction("スタイルを貼り付け")
        paste_style_action.setEnabled(app.transfer.copied_style is not None)
        paste_style_action.triggered.connect(app.transfer.paste_style)
        # 元ファイルを持たないデータセット(貼り付け・演算・プラグインの生成物など)では使えない
        reload_action = menu.addAction("元ファイルから再読み込み")
        reload_action.setEnabled(bool(current.source_file))
        reload_action.triggered.connect(app.transfer.reload_from_source)

        processing = app.processing
        for title, handler in (
            ("規格化(ノーマライズ)...", processing.normalize),
            ("Savitzky-Golayフィルタ(平滑化/微分)...", processing.savgol_smooth),
            ("ベースライン補正...", processing.baseline_correction),
            ("区間積分(台形則/Simpson則)...", processing.interval_integral),
            ("累積積分(台形則/Simpson則)...", processing.cumulative_integral),
            ("共通X格子へのリサンプリング/補間...", processing.resample),
            ("重複X値の検出...", processing.detect_duplicate_x),
            ("行フィルタ...", processing.filter_rows),
            ("列の値で系列に分割...", processing.split_by_column),
            ("外れ値検出(Z-score/IQR)...", processing.detect_outliers),
        ):
            data_proc_menu.addAction(title).triggered.connect(handler)

        for title, handler in (
            ("統計値アンカーラベルを追加...", app.overlays.add_stat_label),
            ("インセット(拡大図)を追加...", app.overlays.add_inset),
            ("ピーク位置に自動ラベルを追加...", app.peaks.add_peak_labels),
            ("ヒストグラム / KDE...", processing.histogram_or_kde),
        ):
            analysis_menu.addAction(title).triggered.connect(handler)

        # 対象外でも隠さずグレーアウトする(ある機能に気づけるように)
        export_fit_action = export_menu.addAction("フィット結果のエクスポート...")
        export_fit_action.setEnabled(current.fit_result is not None)
        export_fit_action.triggered.connect(app.fitting.show_fit_result)
        copy_methods_text_action = export_menu.addAction("「方法」文をコピー...")
        copy_methods_text_action.setEnabled(current.provenance is not None)
        copy_methods_text_action.triggered.connect(app.transfer.copy_methods_text)

    selected = app._get_selected_datasets()
    if len(selected) >= 2:
        if len(selected) == 2:
            multi_menu.addAction("データセット間演算...").triggered.connect(app.processing.arithmetic)
            multi_menu.addAction("X軸アライメント(相互相関)...").triggered.connect(app.processing.align_selected)
        multi_menu.addAction("平均±SD生成...").triggered.connect(app.processing.mean_and_sd_of_selected)
        multi_menu.addAction("バッチ列計算...").triggered.connect(app.processing.batch_column_calculate)
        multi_menu.addAction("バッチカーブフィット...").triggered.connect(app.fitting.batch_fit_selected)

    if selected:
        export_menu.addAction("データ表をファイルに書き出す...").triggered.connect(app.transfer.export_data)
        # 他のタブが無くても出しておき、選んだときに案内する
        tab_menu.addAction("別のタブへコピー...").triggered.connect(
            lambda: app.transfer.copy_or_move_to_tab(move=False))
        tab_menu.addAction("別のタブへ移動...").triggered.connect(
            lambda: app.transfer.copy_or_move_to_tab(move=True))

    attached_any = False
    for sub in submenus:
        if sub.actions():
            if not attached_any:
                menu.addSeparator()
                attached_any = True
            menu.addMenu(sub)

    if app.ui.dataset_list_widget.selectedItems():
        menu.addSeparator()
        menu.addAction("削除").triggered.connect(app._on_remove_dataset)

    menu._graphica_submenus = submenus
    return menu
