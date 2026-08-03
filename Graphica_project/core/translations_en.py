# core/translations_en.py
"""
英語UI翻訳(項目41)。core/i18n.py の register_translations() 経由で登録される。
対象範囲は「主要UI」(メニューバー・主要ボタン・代表的なダイアログ)であり、
データエディタの細かいツールチップ等、露出の少ない文言は未収録(原文の日本語の
まま表示される)。原文(日本語)をキーとした辞書。
"""

TRANSLATIONS = {
    # --- メニューバー: ファイル ---
    "ファイル(&F)": "&File",
    "プロジェクトを開く(&O)...": "&Open Project...",
    "プロジェクトを保存(&P)...": "&Save Project...",
    "クリップボードから貼り付け(&V)...": "Paste from Clipboard(&V)...",
    "最近使ったファイル": "Recent Files",
    "書式テンプレートを保存(&T)...": "Save Style Template(&T)...",
    "書式テンプレートを適用(&A)...": "Apply Style Template(&A)...",
    "名前を付けてエクスポート(&S)...": "Export As(&S)...",
    "グラフをコピー(&C)": "Copy Plot(&C)",
    "印刷(&R)...": "Print(&R)...",
    "バッチエクスポート(&B)...": "Batch Export(&B)...",
    "オートセーブ間隔を設定(&I)...": "Set Autosave Interval(&I)...",
    "オートセーブ: 無効(&I)...": "Autosave: Off(&I)...",
    "オートセーブ: {minutes}分間隔(&I)...": "Autosave: Every {minutes} min(&I)...",

    # --- メニューバー: 編集 ---
    "編集(&E)": "&Edit",
    "元に戻す": "Undo",
    "やり直し": "Redo",
    "環境設定(&P)...": "Preferences(&P)...",
    "コマンドパレット(&K)...": "Command Palette(&K)...",

    # --- メニューバー: 表示 ---
    "表示(&V)": "&View",
    "プロパティパネル": "Properties Panel",
    "エクスポートプレビュー": "Export Preview",
    "ダークモード": "Dark Mode",

    # --- メニューバー: プラグイン ---
    "プラグイン(&P)": "&Plugins",

    # --- メニューバー: ヘルプ ---
    "ヘルプ(&H)": "&Help",
    "mathtext リファレンス...": "mathtext Reference...",
    "列計算機能 リファレンス...": "Column Calculator Reference...",
    "キーボードショートカット一覧...": "Keyboard Shortcuts...",
    "{app} について...": "About {app}...",

    # --- 環境設定ダイアログ: 表示言語 ---
    "表示言語の変更": "Language Changed",
    "表示言語の変更は、次回起動時に反映されます。": "The new display language will take effect the next time you start the app.",

    # --- メインウィンドウ: ツールバー/主要ボタン/パネル見出し ---
    "プロットのプロパティ": "Plot Properties",
    "データカーソル": "Data Cursor",
    "注釈 (クリック:テキスト / ドラッグ:矢印 / 右クリック:削除)": "Annotation (Click: text / Drag: arrow / Right-click: delete)",
    "レイアウト編集 (自由配置レイアウト時のみ: ドラッグでプロットを移動/リサイズ)":
        "Edit Layout (Free layout only: drag to move/resize plots)",
    "プロット複製": "Duplicate Plot",
    "データ表示/編集": "View/Edit Data",
    "曲線フィット": "Curve Fit",
    "ピーク検出": "Find Peaks",
    "自動配色": "Auto Color",
    "パレット管理...": "Manage Palettes...",
    "新しいフォルダ": "New Folder",
    "データセットのプロパティ": "Dataset Properties",
    "グラフ全体レイアウト": "Overall Plot Layout",
    "行数:": "Rows:",
    "列数:": "Columns:",
    "自由配置レイアウト(ドラッグで配置)": "Free Layout (drag to arrange)",
    "+ プロット追加": "+ Add Plot",
    "- プロット削除": "− Remove Plot",
    "編集対象のプロット": "Active Plot",

    # --- このソフトについて ---
    "{app} について": "About {app}",
    "バージョン": "Version",

    # --- ウェルカムダイアログ ---
    "{app} へようこそ": "Welcome to {app}",
    "サンプルデータを開く": "Open Sample Data",
    "閉じる": "Close",

    # --- 環境設定ダイアログ ---
    "環境設定": "Preferences",
    "外観": "Appearance",
    "ダークモードを有効にする": "Enable dark mode",
    "言語": "Language",
    "表示言語:": "Display language:",
    "※ 言語の変更は次回起動時に反映されます。": "* The language change takes effect after restarting the app.",
    "保存": "Save",
    " 分": " min",
    "無効": "Off",
    "オートセーブ間隔:": "Autosave interval:",
}
