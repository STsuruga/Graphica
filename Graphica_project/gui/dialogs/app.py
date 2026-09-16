# gui/dialogs/app.py
"""
アプリ全体(設定・ヘルプ・操作)のダイアログ。

gui/dialogs.py(5,560行・47ダイアログ)を機能群ごとに分割したもの
(改善ボード B-2)。呼び出し側は従来どおり `from gui.dialogs import X` で
参照できる(gui/dialogs/__init__.py が再エクスポートしている)。
"""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QEvent, QUrl, Qt
from PySide6.QtGui import QDesktopServices, QKeySequence
from gui import icon_utils
from gui.theme import apply_form_spacing




#==============================================================================
# カスタムダイアログクラス: 環境設定 (Preferences)
#==============================================================================
class PreferencesDialog(QDialog):
    """
    これまでメニューに散らばっていた設定項目 (ダークモード、オートセーブ間隔) を
    1つの画面にまとめた環境設定ダイアログ。
    設定の永続化自体は呼び出し側 (main_window) が get_settings() の戻り値を
    使って行う。このダイアログ自体は値の入力/表示のみを担当する。
    """

    def __init__(self, dark_mode, autosave_minutes, autosave_bounds=(0, 180), parent=None,
                 current_language=None, autosave_dir="", point_label_max_points=1000,
                 snap_to_grid_enabled=False, snap_grid_interval_px=10,
                 plugin_records=None, plugin_registration_errors=None, disabled_plugin_names=None):
        """
        plugin_records/plugin_registration_errors/disabled_plugin_names は
        「プラグイン」タブ(項目F-2)用。呼び出し側(gui/mixins/project_io_mixin.py)
        が core.plugin_api.get_loaded_plugin_records() 等をそのまま渡す想定。
        plugin_records=None は「一度もロードされていない(セーフモード含む)」を表し、
        空リストの「1つも無い」とは区別して表示する。
        """
        super().__init__(parent)
        from core.i18n import tr, SUPPORTED_LANGUAGES, get_language
        self.setWindowTitle(tr("環境設定"))
        # ★ QGroupBoxの見出しをアクセントカラーの背景チップで目立たせるQSS
        #   (GUIモダン化第2弾、項目68)により、各グループボックスの上部余白
        #   (margin-top/padding-top)が以前より広くなったため、旧来のサイズ
        #   (360x260)のままだと3つのグループボックスがすべて収まりきらず
        #   文字が見切れてしまっていた。縦方向に余裕を持たせる。
        # 項目F-2でプラグイン管理タブを追加したため、さらに縦横に余裕を持たせる。
        self.resize(480, 520)

        outer_layout = QVBoxLayout(self)
        tabs = QTabWidget()
        outer_layout.addWidget(tabs)

        general_tab = QWidget()
        layout = QVBoxLayout(general_tab)
        tabs.addTab(general_tab, tr("一般"))

        appearance_group = QGroupBox(tr("外観"))
        appearance_layout = QVBoxLayout(appearance_group)
        self.dark_mode_checkbox = QCheckBox(tr("ダークモードを有効にする"))
        self.dark_mode_checkbox.setChecked(bool(dark_mode))
        appearance_layout.addWidget(self.dark_mode_checkbox)
        layout.addWidget(appearance_group)

        # UIの多言語対応(項目41): 表示言語の選択。切り替えは次回起動時に反映される
        # (実行中のウィジェットをその場で再翻訳する仕組みは持たないため)。
        language_group = QGroupBox(tr("言語"))
        language_form = QFormLayout(language_group)
        self.language_combo = QComboBox()
        self._language_codes = list(SUPPORTED_LANGUAGES.keys())
        self.language_combo.addItems([SUPPORTED_LANGUAGES[code] for code in self._language_codes])
        active_language = current_language or get_language()
        if active_language in self._language_codes:
            self.language_combo.setCurrentIndex(self._language_codes.index(active_language))
        language_form.addRow(tr("表示言語"), self.language_combo)
        language_note = QLabel(tr("※ 言語の変更は次回起動時に反映されます。"))
        language_note.setStyleSheet("font-size: 9pt; color: gray;")
        language_note.setWordWrap(True)
        language_form.addRow(language_note)
        layout.addWidget(language_group)

        save_group = QGroupBox(tr("保存"))
        save_form = QFormLayout(save_group)
        self.autosave_spinbox = QSpinBox()
        min_minutes, max_minutes = autosave_bounds
        self.autosave_spinbox.setRange(min_minutes, max_minutes)
        self.autosave_spinbox.setSuffix(tr(" 分"))
        self.autosave_spinbox.setSpecialValueText(tr("無効"))
        self.autosave_spinbox.setValue(int(autosave_minutes))
        save_form.addRow(tr("オートセーブ間隔"), self.autosave_spinbox)

        # オートセーブの保存先フォルダ(未指定なら従来どおりアプリのフォルダに保存)
        self._autosave_dir = autosave_dir or ""
        autosave_dir_row = QHBoxLayout()
        self.autosave_dir_edit = QLineEdit(self._autosave_dir)
        self.autosave_dir_edit.setReadOnly(True)
        self.autosave_dir_edit.setPlaceholderText(tr("(既定: アプリのフォルダ)"))
        self.autosave_dir_browse_button = QPushButton(tr("参照..."))
        self.autosave_dir_browse_button.setIcon(icon_utils.icon("folder"))
        self.autosave_dir_browse_button.clicked.connect(self._on_browse_autosave_dir)
        self.autosave_dir_clear_button = QPushButton(tr("既定に戻す"))
        self.autosave_dir_clear_button.setIcon(icon_utils.icon("refresh"))
        self.autosave_dir_clear_button.clicked.connect(self._on_clear_autosave_dir)
        autosave_dir_row.addWidget(self.autosave_dir_edit, 1)
        autosave_dir_row.addWidget(self.autosave_dir_browse_button)
        autosave_dir_row.addWidget(self.autosave_dir_clear_button)
        save_form.addRow(tr("オートセーブ保存先"), autosave_dir_row)

        layout.addWidget(save_group)

        # パフォーマンス(項目105): データ点ラベル表示は点数が多いと ax.annotate() の
        # 呼び出し回数がそのまま増え、アプリがフリーズする原因になる。この件数を
        # 超えるデータセットには自動的にラベルを描画しないようにする上限を設定できる。
        performance_group = QGroupBox(tr("パフォーマンス"))
        performance_form = QFormLayout(performance_group)
        self.point_label_max_spinbox = QSpinBox()
        self.point_label_max_spinbox.setRange(10, 1_000_000)
        self.point_label_max_spinbox.setSingleStep(100)
        self.point_label_max_spinbox.setSuffix(tr(" 点"))
        self.point_label_max_spinbox.setValue(int(point_label_max_points))
        self.point_label_max_spinbox.setToolTip(tr(
            "データ点にラベルを表示する機能は、データ点数が多いと描画が重くなり、"
            "アプリがフリーズする場合があります。この件数を超えるデータセットには、"
            "ラベルを有効にしていても自動的に表示しません。"
        ))
        performance_form.addRow(tr("データ点ラベルの表示上限"), self.point_label_max_spinbox)
        layout.addWidget(performance_group)

        # スナップ・トゥ・グリッド(項目84): テキスト注釈・矢印注釈をドラッグ配置する際、
        # ピクセル単位のグリッドに位置を吸着させ、複数の注釈をきれいに整列できるようにする。
        annotation_group = QGroupBox(tr("注釈"))
        annotation_layout = QVBoxLayout(annotation_group)
        self.snap_to_grid_checkbox = QCheckBox(tr("スナップ・トゥ・グリッドを有効にする"))
        self.snap_to_grid_checkbox.setChecked(bool(snap_to_grid_enabled))
        annotation_layout.addWidget(self.snap_to_grid_checkbox)
        annotation_form = QFormLayout()
        self.snap_grid_interval_spinbox = QSpinBox()
        self.snap_grid_interval_spinbox.setRange(1, 200)
        self.snap_grid_interval_spinbox.setSuffix(tr(" px"))
        self.snap_grid_interval_spinbox.setValue(int(snap_grid_interval_px))
        annotation_form.addRow(tr("グリッド間隔"), self.snap_grid_interval_spinbox)
        annotation_layout.addLayout(annotation_form)
        layout.addWidget(annotation_group)

        layout.addStretch()

        # --- 「プラグイン」タブ(項目F-2) ---
        plugin_tab = QWidget()
        plugin_tab_layout = QVBoxLayout(plugin_tab)
        tabs.addTab(plugin_tab, tr("プラグイン"))

        # インストール・プラグインフォルダを開く(いずれもOK/Cancelフローとは
        # 独立した即時実行のボタン。オートセーブ保存先の参照ボタンと同じ位置づけ)
        plugin_actions_row = QHBoxLayout()
        self.install_plugin_button = QPushButton(tr("プラグインをインストール..."))
        self.install_plugin_button.setIcon(icon_utils.icon("download"))
        self.install_plugin_button.clicked.connect(self._on_install_plugin)
        # ★ 実機フィードバック: 「ボタンが一回押すと他のボタン押すまでずっと
        #   色付きになる」。QPushButtonの既定フォーカスポリシー(StrongFocus/
        #   ClickFocus)によりクリック後もフォーカスの青枠が残り続けるため、
        #   即時実行ボタン(OK/Cancelフローとは独立)はフォーカスを持たせない。
        self.install_plugin_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        plugin_actions_row.addWidget(self.install_plugin_button)
        self.open_plugins_folder_button = QPushButton(tr("プラグインフォルダを開く"))
        self.open_plugins_folder_button.setIcon(icon_utils.icon("folder"))
        self.open_plugins_folder_button.clicked.connect(self._on_open_plugins_folder)
        self.open_plugins_folder_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        plugin_actions_row.addWidget(self.open_plugins_folder_button)
        plugin_actions_row.addStretch()
        plugin_tab_layout.addLayout(plugin_actions_row)

        # ロード済みプラグインの一覧(名前/バージョン/作者)+ 個別ON/OFF。
        # チェック状態はダイアログを閉じる際にget_disabled_plugin_names()経由で
        # 読み取られ、QSettingsへの反映(次回起動時に反映)は呼び出し側
        # (gui/mixins/project_io_mixin.py の _on_show_preferences)が行う。
        loaded_group = QGroupBox(tr("読み込み済みプラグイン"))
        loaded_layout = QVBoxLayout(loaded_group)
        self.plugin_list = QListWidget()
        self._disabled_plugin_names = set(disabled_plugin_names or [])
        self._populate_plugin_list(plugin_records, self._disabled_plugin_names)
        loaded_layout.addWidget(self.plugin_list)
        plugin_tab_layout.addWidget(loaded_group, 1)

        # フック単位の登録失敗(項目A-2): プラグイン全体としてはロードに成功して
        # いても、個々のregister_xxx呼び出しが(名前衝突等で)失敗している場合に
        # ここに表示する(get_loaded_plugin_recordsのerrorには現れないため)。
        hook_errors_group = QGroupBox(tr("フック単位の登録エラー"))
        hook_errors_layout = QVBoxLayout(hook_errors_group)
        self.plugin_hook_errors_list = QListWidget()
        self._populate_hook_errors_list(plugin_registration_errors)
        hook_errors_layout.addWidget(self.plugin_hook_errors_list)
        plugin_tab_layout.addWidget(hook_errors_group)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        outer_layout.addWidget(button_box)

        apply_form_spacing(self)

    def _populate_plugin_list(self, plugin_records, disabled_names):
        """
        「読み込み済みプラグイン」リストを構築する。plugin_records=Noneは
        「一度もロードされていない」(セーフモード中含む)ことを表す特別扱いの
        1行を出す。各行のチェック状態は現在の無効化設定を反映する(表示専用の
        行=状態未読込プラグイン向けエラー行にはチェックボックスを付けない)。
        """
        from core.i18n import tr
        self.plugin_list.clear()
        if plugin_records is None:
            item = QListWidgetItem(tr("(プラグインは読み込まれていません)"))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            self.plugin_list.addItem(item)
            return
        if not plugin_records:
            item = QListWidgetItem(tr("(プラグインはありません)"))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            self.plugin_list.addItem(item)
            return

        for record in plugin_records:
            name = record["name"]
            info = record.get("info")
            error = record.get("error")
            disabled = record.get("disabled", False)

            if disabled:
                label = tr("{name} (無効化中)").format(name=name)
            elif error:
                label = tr("{name} — エラー: {error}").format(name=name, error=error)
            elif info:
                label = f"{info.get('name', name)} v{info.get('version', '?')} — {info.get('author', '?')}"
            else:
                label = name

            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Unchecked if name in disabled_names else Qt.CheckState.Checked
            )
            self.plugin_list.addItem(item)

    def _populate_hook_errors_list(self, plugin_registration_errors):
        from core.i18n import tr
        self.plugin_hook_errors_list.clear()
        if not plugin_registration_errors:
            item = QListWidgetItem(tr("(フック単位の登録エラーはありません)"))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            self.plugin_hook_errors_list.addItem(item)
            return
        for error in plugin_registration_errors:
            text = f"[{error.plugin_name}] {error.hook_kind.value}: {error.message}"
            self.plugin_hook_errors_list.addItem(QListWidgetItem(text))

    def get_disabled_plugin_names(self):
        """
        「読み込み済みプラグイン」リストの現在のチェック状態から、無効化された
        (チェックが外された)プラグイン名の集合を返す。呼び出し側がこれを
        QSettingsのDISABLED_PLUGINS_SETTINGS_KEYへ保存する(次回起動時に反映)。
        """
        disabled = set()
        for i in range(self.plugin_list.count()):
            item = self.plugin_list.item(i)
            name = item.data(Qt.ItemDataRole.UserRole)
            if name is not None and item.checkState() == Qt.CheckState.Unchecked:
                disabled.add(name)
        return disabled

    def _on_open_plugins_folder(self):
        from core.app_paths import get_user_plugins_dir
        QDesktopServices.openUrl(QUrl.fromLocalFile(get_user_plugins_dir()))

    def _on_browse_autosave_dir(self):
        from core.i18n import tr
        directory = QFileDialog.getExistingDirectory(
            self, tr("オートセーブの保存先を選択"), self._autosave_dir or ""
        )
        if directory:
            self._autosave_dir = directory
            self.autosave_dir_edit.setText(directory)

    def _on_clear_autosave_dir(self):
        self._autosave_dir = ""
        self.autosave_dir_edit.setText("")

    def _on_install_plugin(self):
        from core.i18n import tr
        zip_path, _ = QFileDialog.getOpenFileName(
            self, tr("プラグインをインストール"), "", tr("Zip files (*.zip)")
        )
        if not zip_path:
            return

        from core.plugin_install import install_plugin_zip, PluginInstallError
        try:
            installed_name = install_plugin_zip(zip_path)
        except PluginInstallError as e:
            QMessageBox.critical(self, tr("インストール失敗"), str(e))
            return

        QMessageBox.information(
            self, tr("インストール完了"),
            tr("プラグイン '{name}' をインストールしました。次回起動時に有効になります。").format(
                name=installed_name
            ),
        )

    def get_settings(self):
        """
        Returns:
            tuple (bool, int, str, str, int, bool, int): (ダークモードを有効にするか,
                オートセーブ間隔(分, 0=無効), 表示言語コード,
                オートセーブ保存先ディレクトリ("" なら既定=アプリのフォルダ),
                データ点ラベルの表示上限(件数),
                スナップ・トゥ・グリッドを有効にするか, グリッド間隔(px))
        """
        language_code = self._language_codes[self.language_combo.currentIndex()]
        return (self.dark_mode_checkbox.isChecked(), self.autosave_spinbox.value(),
                language_code, self._autosave_dir, self.point_label_max_spinbox.value(),
                self.snap_to_grid_checkbox.isChecked(), self.snap_grid_interval_spinbox.value())




#==============================================================================
# カスタムダイアログクラス (1)
#==============================================================================
class HelpDialog(QDialog):
    """
    Matplotlib の mathtext (数式表示機能) の簡易リファレンスを表示する
    ヘルプダイアログクラスです。
    """

    def __init__(self, parent=None):
        """
        ダイアログの初期化を行います。
        
        Args:
            parent (QWidget, optional): 親ウィジェット。
        """
        super().__init__(parent)
        self.setWindowTitle("mathtext クイックリファレンス")
        self.resize(600, 700) # ウィンドウサイズを固定（リサイズ可能にする場合は resize の代わりに setMinimumSize なども検討）

        # メインレイアウトとして QVBoxLayout (垂直レイアウト) を設定
        layout = QVBoxLayout(self)

        # HTML を表示するための QTextBrowser を作成
        text_browser = QTextBrowser()
        text_browser.setReadOnly(True) # 閲覧専用に設定
        text_browser.setOpenExternalLinks(True) # (もしHTML内にリンクがあれば) 外部ブラウザで開く

        # --- リファレンスの内容をHTMLで定義 ---
        # r"""...""" (Raw Triple-Quoted String) を使うことで、
        # バックスラッシュ '\' をエスケープシーケンスとして解釈させず、
        # LaTeX のコマンド (例: \mathbf) をそのまま記述できます。
        help_html = r"""
        <h1>Matplotlib Mathtext クイックリファレンス</h1>
        <p>
            <code>mathtext</code> は、プロットラベル（タイトル、軸ラベル、凡例など）に、LaTeXのような数式や特殊文字を簡単に入力するための機能です。
        </p>
        <p>
            テキストボックスに入力する文字列を <b>$</b>（ドルマーク）で囲むと、その中身が数式として解釈されます。
        </p>
        
        <hr>
        
        <h2>1. 基本的な書式 (太字・イタリック) 🎨</h2>
        <p>ラベルの一部分、または全体を特定の書式に変更できます。</p>
        <ul>
            <li><b>太字 (Bold)</b>: <code>$\mathbf{...}$</code></li>
            <li><b>イタリック (Italic)</b>: <code>$\mathit{...}$</code></li>
            <li><b>立体 (Roman/標準)</b>: <code>$\mathrm{...}$</code></li>
        </ul>
        
        <h4>✅ 組み合わせの例</h4>
        <p>「<b>Speed</b> (<i>v</i>)」と表示したい場合：</p>
        <p><b>入力</b>: <code>$\mathbf{Speed}\ \mathit{(v)}$</code></p>
        <p>
            <ul>
                <li><code>\ </code> (バックスラッシュ + スペース) は、数式内で強制的にスペースを入れたい場合に使います。</li>
            </ul>
        </p>
        <p>「Velocity (m/s)」のように、イタリックにしたくない単位（立体にしたい）場合：</p>
        <p><b>入力</b>: <code>$\mathrm{Velocity\ (m/s)}$</code></p>

        <hr>

        <h2>2. 上付き文字 と 下付き文字</h2>
        <ul>
            <li><b>上付き文字</b>: <code>^</code> （ハット）</li>
            <li><b>下付き文字</b>: <code>_</code> （アンダースコア）</li>
        </ul>
        <p>文字が1文字以上の場合は、<code>{}</code>（中括弧）で囲みます。</p>
        
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr class="header-row">
                <th>表示したい文字</th>
                <th>入力するテキスト</th>
            </tr>
            <tr>
                <td>10<sup>3</sup></td>
                <td><code>$10^3$</code></td>
            </tr>
            <tr>
                <td>10<sup>-3</sup></td>
                <td><code>$10^{-3}$</code></td>
            </tr>
            <tr>
                <td>V<sub>max</sub></td>
                <td><code>$V_{\mathrm{max}}$</code></td>
            </tr>
            <tr>
                <td>k<sub>B</sub></td>
                <td><code>$k_{\mathrm{B}}$</code></td>
            </tr>
        </table>
        
        <hr>
        
        <h2>3. よく使う特殊文字・記号 🇬🇷</h2>
        
        <h4>ギリシャ文字</h4>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr class="header-row">
                <th>表示したい文字</th>
                <th>入力するテキスト</th>
            </tr>
            <tr><td>&alpha; (アルファ)</td><td><code>$\alpha$</code></td></tr>
            <tr><td>&beta; (ベータ)</td><td><code>$\beta$</code></td></tr>
            <tr><td>&gamma; (ガンマ)</td><td><code>$\gamma$</code></td></tr>
            <tr><td>&Delta; (デルタ大文字)</td><td><code>$\Delta$</code></td></tr>
            <tr><td>&delta; (デルタ小文字)</td><td><code>$\delta$</code></td></tr>
            <tr><td>&epsilon; (イプシロン)</td><td><code>$\epsilon$</code></td></tr>
            <tr><td>&mu; (ミュー)</td><td><code>$\mu$</code></td></tr>
            <tr><td>&pi; (パイ)</td><td><code>$\pi$</code></td></tr>
            <tr><td>&rho; (ロー)</td><td><code>$\rho$</code></td></tr>
            <tr><td>&Sigma; (シグマ大文字)</td><td><code>$\Sigma$</code></td></tr>
            <tr><td>&sigma; (シグマ小文字)</td><td><code>$\sigma$</code></td></tr>
            <tr><td>&tau; (タウ)</td><td><code>$\tau$</code></td></tr>
            <tr><td>&Omega; (オメガ大文字)</td><td><code>$\Omega$</code></td></tr>
            <tr><td>&omega; (オメガ小文字)</td><td><code>$\omega$</code></td></tr>
        </table>

        <h4>単位・記号</h4>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr class="header-row">
                <th>表示したい文字</th>
                <th>入力するテキスト</th>
            </tr>
            <tr><td>°C (温度)</td><td><code>$^{\circ}$C</code></td></tr>
            <tr><td>&pm; (プラスマイナス)</td><td><code>$\pm$</code></td></tr>
            <tr><td>&middot; (中点ドット)</td><td><code>$\cdot$</code></td></tr>
            <tr><td>&times; (掛ける)</td><td><code>$\times$</code></td></tr>
            <tr><td>&approx; (ほぼイコール)</td><td><code>$\approx$</code></td></tr>
        </table>

        <hr>
        
        <h2>4. 分数 と 根号</h2>
        <ul>
            <li><b>分数</b>: <code>$\frac{分子}{分母}$</code> (例: <code>$\frac{1}{2}$</code>)</li>
            <li><b>平方根 (ルート)</b>: <code>$\sqrt{...}$</code> (例: <code>$\sqrt{2}$</code>)</li>
        </ul>

        <hr>

        <h2>5. 総和・積分・極限などの演算子</h2>
        <p>
            <code>^</code>・<code>_</code>と組み合わせて、上下に添え字を付けられます。
        </p>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr class="header-row">
                <th>表示したい記号</th>
                <th>入力するテキスト</th>
            </tr>
            <tr><td>&sum; (総和)</td><td><code>$\sum_{i=0}^{n}$</code></td></tr>
            <tr><td>&prod; (総乗)</td><td><code>$\prod_{i=1}^{n}$</code></td></tr>
            <tr><td>&int; (積分)</td><td><code>$\int_{0}^{\infty}$</code></td></tr>
            <tr><td>&part; (偏微分)</td><td><code>$\partial$</code></td></tr>
            <tr><td>&nabla; (ナブラ)</td><td><code>$\nabla$</code></td></tr>
            <tr><td>&infin; (無限大)</td><td><code>$\infty$</code></td></tr>
        </table>

        <h4>矢印・比較演算子</h4>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr class="header-row">
                <th>表示したい記号</th>
                <th>入力するテキスト</th>
            </tr>
            <tr><td>&rarr; (右矢印)</td><td><code>$\rightarrow$</code></td></tr>
            <tr><td>&harr; (両矢印)</td><td><code>$\leftrightarrow$</code></td></tr>
            <tr><td>&le; (以下)</td><td><code>$\leq$</code></td></tr>
            <tr><td>&ge; (以上)</td><td><code>$\geq$</code></td></tr>
            <tr><td>&ne; (等しくない)</td><td><code>$\neq$</code></td></tr>
        </table>

        <h4>文字の上に記号を付ける</h4>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr class="header-row">
                <th>表示したい記号</th>
                <th>入力するテキスト</th>
            </tr>
            <tr><td>x&#772; (上線・平均値など)</td><td><code>$\overline{x}$</code></td></tr>
            <tr><td>x&#8407; (ベクトル)</td><td><code>$\vec{x}$</code></td></tr>
            <tr><td>x&#770; (ハット)</td><td><code>$\hat{x}$</code></td></tr>
        </table>

        <p style="color:#888; margin-top: 12px;">
            ※ ここに載っている記法は、いずれもタイトル/軸ラベル欄にそのまま
            半角文字で入力すれば動作します(<code>Aa</code>ボタンの装飾メニューに
            あるΩボタンからも、よく使うギリシャ文字を選択部分の挿入なしでカーソル
            位置に差し込めます)。<br>
            なお、これは matplotlib 内蔵の軽量な数式パーサー(mathtext)であり、
            <code>\begin{matrix}</code> のような複雑なLaTeX環境や外部LaTeXパッケージ
            には対応していません。
        </p>
        """
        # ★ 項目H-2-6(実機での目視確認で発覚): 表内の見出し行はHTML内に
        #   `background-color: #f0f0f0`のような固定の薄いグレーをハード
        #   コードしていたため、ダークモードでは見出しセルがほぼ見えない
        #   薄グレーの塊になり、文字も読めなくなっていた(ライトモードは
        #   問題なかった)。見出し行はクラス名(class="header-row")だけを
        #   HTML側に残し、実際の色はQTextDocumentのdefault stylesheetで
        #   現在のテーマトークンから注入することで、ダーク/ライト両方で
        #   読めるようにする。
        self._text_browser = text_browser
        self.refresh_theme()
        # HTMLコンテンツを QTextBrowser にセット
        text_browser.setHtml(help_html)
        # --- HTML定義ここまで ---

        # レイアウトにテキストブラウザを追加
        layout.addWidget(text_browser)

        # --- 閉じるボタンの追加 ---
        # QDialogButtonBox を使うと、プラットフォーム標準のボタン配置（OK, Cancel, Closeなど）
        # を簡単に実現できます。
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)

        # 'rejected' シグナル（CloseボタンやEscキー押下で発生）を、
        # QDialog の標準スロット 'reject'（ダイアログを閉じる処理）に接続します。
        button_box.rejected.connect(self.reject)

        # レイアウトにボタンボックスを追加
        layout.addWidget(button_box)

    def refresh_theme(self):
        """
        表見出し行(tr.header-row)の色を現在のテーマトークンに合わせて
        再適用する。このダイアログは非モーダル(show())で開いたまま
        メインウィンドウを操作できるため、開いたままダークモードを
        切り替えられると、__init__時点のトークンで固定していた色が
        古いテーマのまま取り残されるバグがあった
        (gui/mixins/ui_setup_mixin.py の _on_toggle_dark_mode から呼ばれる)。
        """
        from gui import theme
        _tokens = theme.current_tokens()
        self._text_browser.document().setDefaultStyleSheet(
            f"tr.header-row {{ background-color: {_tokens['surface_2']}; "
            f"color: {_tokens['text_primary']}; }}"
        )




#==============================================================================
# カスタムダイアログクラス (0): このソフトについて
#==============================================================================
class AboutDialog(QDialog):
    """
    「このソフトについて」ダイアログ。
    バージョン番号 (core/version.py で一元管理) と、使用しているOSSライブラリの
    ライセンス表記をまとめて表示する。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        from core.version import APP_NAME, __version__
        from core.i18n import tr

        self.setWindowTitle(tr("{app} について").format(app=APP_NAME))
        self.resize(420, 380)

        layout = QVBoxLayout(self)

        if parent is not None:
            icon_label = QLabel()
            pixmap = parent.windowIcon().pixmap(64, 64)
            if not pixmap.isNull():
                icon_label.setPixmap(pixmap)
                icon_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                layout.addWidget(icon_label)

        title_label = QLabel(f"<h2>{APP_NAME}</h2>")
        title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title_label)

        version_label = QLabel(f"{tr('バージョン')} {__version__}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(version_label)

        credits_browser = QTextBrowser()
        credits_browser.setOpenExternalLinks(True)
        credits_browser.setHtml(r"""
        <p>Graphica は、CSV/Excelファイルからデータを読み込み、グラフの作成・編集・
        エクスポートを行うためのデータ可視化ソフトウェアです。</p>
        <h3>ライセンス</h3>
        <p>Graphica 本体は <b>MIT License</b> で提供しています
        (Copyright (c) 2026 STsuruga)。ソースコードは
        <a href="https://github.com/STsuruga/Graphica">GitHub</a> で公開しています。</p>
        <h3>使用ライブラリ</h3>
        <ul>
            <li>PySide6 / Qt (LGPL v3)</li>
            <li>Matplotlib (PSFベースのライセンス)</li>
            <li>NumPy (BSD 3-Clause)</li>
            <li>pandas (BSD 3-Clause)</li>
            <li>SciPy (BSD 3-Clause)</li>
            <li>openpyxl (MIT)</li>
            <li>Tabler Icons (MIT) — アプリ内のアイコン</li>
        </ul>
        <p>このアプリに同梱している Qt / PySide6 は LGPL v3 です。同梱物の一覧と
        再配布時の注意は、配布物に含まれる <code>THIRD_PARTY_LICENSES.md</code> を
        参照してください。各ライブラリの詳細な条文は、それぞれの配布元をご確認ください。</p>
        """)
        layout.addWidget(credits_browser)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)




#==============================================================================
# カスタムダイアログクラス: 初回起動時のウェルカム画面
#==============================================================================
class WelcomeDialog(QDialog):
    """
    初回起動時に表示するウェルカムダイアログ兼スタートアップ画面(項目C-912)。
    簡単な操作ガイド(チュートリアル)・すぐに試せるサンプルデータの読み込み・
    最近使ったファイルへの入口・書式テンプレートを開く入口をまとめて提供する。

    初回起動時(gui/main_window.pyの_check_first_launch、has_shown_welcome
    QSettingsフラグで一度きり)に加え、「ファイル」メニューの
    「スタートアップ画面...」(_on_show_startup_screen)からいつでも同じ内容を
    開ける。呼び出し元は、閉じた後に load_sample_requested/selected_recent_file/
    load_template_requested のいずれが立っているかを見て、対応する処理
    (サンプル読込/該当ファイルを開く/書式テンプレート読込ダイアログを開く)を行う
    (このダイアログ自身はファイルI/Oを一切行わない、意思表示のみの役割)。
    """

    def __init__(self, parent=None, recent_files=None):
        super().__init__(parent)
        import os
        from core.version import APP_NAME
        from core.i18n import tr

        self.setWindowTitle(tr("{app} へようこそ").format(app=APP_NAME))
        self.resize(480, 560)
        self.load_sample_requested = False
        self.selected_recent_file = None
        self.load_template_requested = False
        self._recent_file_paths = list(recent_files) if recent_files else []

        layout = QVBoxLayout(self)

        if parent is not None:
            icon_label = QLabel()
            pixmap = parent.windowIcon().pixmap(64, 64)
            if not pixmap.isNull():
                icon_label.setPixmap(pixmap)
                icon_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
                layout.addWidget(icon_label)

        title_label = QLabel(f"<h2>{tr('{app} へようこそ').format(app=APP_NAME)}</h2>")
        title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(title_label)

        guide_browser = QTextBrowser()
        guide_browser.setHtml(r"""
        <p>{app}は、CSV/Excelファイルからデータを読み込み、グラフの作成・編集・
        エクスポートを行うためのデータ可視化ソフトウェアです。</p>
        <h3>はじめの一歩</h3>
        <ol>
            <li>画面下部の<b>「データ追加」</b>ボタン、または「ファイル」メニューの「データファイルを開く」でCSV/Excelファイルを読み込む
                (下の「サンプルデータを開く」からすぐに試すこともできます)</li>
            <li>X軸・Y軸に使う列を選択する</li>
            <li>右側の「データセットのプロパティ」パネルで色・線種・マーカーなどを調整する</li>
            <li>「曲線フィット」「ピーク検出」などの解析機能を試す</li>
            <li>「ファイル」メニューの「エクスポート」▸「名前を付けてエクスポート」で画像として保存する</li>
        </ol>
        <p>この画面は初回起動時に表示されます。「ファイル」メニューの
        「スタートアップ画面...」からいつでも開けます。</p>
        """.format(app=APP_NAME))
        guide_browser.setMaximumHeight(180)
        layout.addWidget(guide_browser)

        # 最近使ったファイル(項目C-912)。履歴が無い場合(主に初回起動時)は
        # そもそも何も選べないため、セクション自体を表示しない。
        if self._recent_file_paths:
            recent_group = QGroupBox(tr("最近使ったファイル"))
            recent_layout = QVBoxLayout(recent_group)
            self.recent_list = QListWidget()
            for path in self._recent_file_paths:
                item = QListWidgetItem(os.path.basename(path))
                item.setToolTip(path)
                self.recent_list.addItem(item)
            self.recent_list.itemDoubleClicked.connect(self._on_recent_item_double_clicked)
            recent_layout.addWidget(self.recent_list)
            open_recent_button = QPushButton(tr("選択したファイルを開く"))
            open_recent_button.clicked.connect(self._on_open_recent_clicked)
            recent_layout.addWidget(open_recent_button)
            layout.addWidget(recent_group)
        else:
            self.recent_list = None

        button_row = QHBoxLayout()
        self.load_sample_button = QPushButton(tr("サンプルデータを開く"))
        self.load_sample_button.clicked.connect(self._on_load_sample_clicked)
        button_row.addWidget(self.load_sample_button)

        self.load_template_button = QPushButton(tr("書式テンプレートを開く..."))
        self.load_template_button.clicked.connect(self._on_load_template_clicked)
        button_row.addWidget(self.load_template_button)
        button_row.addStretch()

        close_button = QPushButton(tr("閉じる"))
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

    def _on_load_sample_clicked(self):
        self.load_sample_requested = True
        self.accept()

    def _on_open_recent_clicked(self):
        row = self.recent_list.currentRow() if self.recent_list is not None else -1
        if row < 0:
            return
        self.selected_recent_file = self._recent_file_paths[row]
        self.accept()

    def _on_recent_item_double_clicked(self, item):
        row = self.recent_list.row(item)
        self.selected_recent_file = self._recent_file_paths[row]
        self.accept()

    def _on_load_template_clicked(self):
        self.load_template_requested = True
        self.accept()




#==============================================================================
# カスタムダイアログクラス: キーボードショートカット一覧
#==============================================================================
class ShortcutsDialog(QDialog):
    """
    ヘルプメニューから開く、現在使えるキーボードショートカットの一覧ダイアログ。
    メニューバーを直接走査するため、ショートカットを追加/変更してもここを
    個別に更新し忘れる心配がない(CommandPaletteDialogと同じ collect_fn 方式)。
    """

    def __init__(self, collect_fn, parent=None):
        """
        Args:
            collect_fn (callable): 呼ぶたびに現在のメニューアクションを
                [(パスのリスト, QAction), ...] として新しく収集して返す関数。
        """
        super().__init__(parent)
        self.setWindowTitle("キーボードショートカット一覧")
        self.resize(420, 380)

        layout = QVBoxLayout(self)

        table = QTableWidget()
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["操作", "ショートカット"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.verticalHeader().setVisible(False)

        rows = []
        for path, action in collect_fn():
            # ★ QUndoStack.createUndoAction() 等、self.xxx として保持されていない
            # QAction はPython側のラッパーがGCで無効化されうる(既知のPySide6の癖)。
            # 収集直後の使用でも起こりうるため、個別に握りつぶして続行する。
            try:
                shortcut = action.shortcut()
            except RuntimeError:
                continue
            if shortcut.isEmpty():
                continue
            rows.append((" > ".join(path), shortcut.toString(QKeySequence.SequenceFormat.NativeText)))

        table.setRowCount(len(rows))
        for row_idx, (label, shortcut_text) in enumerate(rows):
            table.setItem(row_idx, 0, QTableWidgetItem(label))
            table.setItem(row_idx, 1, QTableWidgetItem(shortcut_text))
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)

        close_button = QPushButton("閉じる")
        close_button.clicked.connect(self.reject)
        layout.addWidget(close_button, alignment=Qt.AlignmentFlag.AlignRight)




#==============================================================================
# カスタムダイアログクラス: コマンドパレット
#==============================================================================
class CommandPaletteDialog(QDialog):
    """
    Ctrl+Shift+P で開く、メニュー項目をキーボードで検索して実行できるダイアログ。
    検索欄にフォーカスがある状態のまま上下キーでリストの選択を移動し、
    Enterで実行できるようにしている(一般的なコマンドパレットのUXに合わせる)。

    ★ 注意 ★
    QMenu.addAction(text) の戻り値のように、Python側で明示的に self.xxx として
    保持されていない QAction は、後からPythonの参照だけを保持していても、
    ガベージコレクションのタイミングでラッパーが無効化される(実体は
    メニューに残っているのに "already deleted" になる)ことがある。
    そのため、収集した (path, action) の組は一度きりの表示にしか使わず、
    実際に実行する際は collect_fn() を呼び直して「今」有効なQActionを
    取り直してからその場で trigger() する(取得と使用の間に時間を空けない)。
    """

    def __init__(self, collect_fn, parent=None):
        """
        Args:
            collect_fn (callable): 呼ぶたびに現在のメニューアクションを
                [(パスのリスト, QAction), ...] として新しく収集して返す関数。
        """
        super().__init__(parent)
        self.setWindowTitle("コマンドパレット")
        self.resize(480, 420)

        self._collect_fn = collect_fn

        layout = QVBoxLayout(self)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("コマンドを検索...")
        layout.addWidget(self.search_edit)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        self.search_edit.textChanged.connect(self._update_list)
        self.list_widget.itemActivated.connect(self._on_item_activated)
        self.search_edit.installEventFilter(self)

        self._update_list("")

    def _update_list(self, text):
        query = text.strip().lower()
        self.list_widget.clear()
        for path, action in self._collect_fn():
            if not action.isEnabled():
                continue
            label = " > ".join(path)
            if query and query not in label.lower():
                continue
            item = QListWidgetItem(label)
            if action.isCheckable():
                item.setText(f"{'✓' if action.isChecked() else ' '}  {label}")
            # QAction そのものではなく、後で再検索するためのパスだけを保持する
            # (プレーンなPythonのリストなので、ラッパー無効化の影響を受けない)
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.list_widget.addItem(item)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _on_item_activated(self, item):
        target_path = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        if target_path is None:
            return
        # 表示時に集めた QAction は使わず、実行直前に取り直したものを使う
        for path, action in self._collect_fn():
            if path == target_path:
                action.trigger()
                return

    def eventFilter(self, obj, event):
        """
        検索欄(QLineEdit)にフォーカスがある間も、上下キーでリストの選択を
        移動でき、Enterで実行できるようにする。
        """
        if obj is self.search_edit and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                row = min(self.list_widget.currentRow() + 1, self.list_widget.count() - 1)
                self.list_widget.setCurrentRow(row)
                return True
            elif key == Qt.Key.Key_Up:
                row = max(self.list_widget.currentRow() - 1, 0)
                self.list_widget.setCurrentRow(row)
                return True
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                current = self.list_widget.currentItem()
                if current is not None:
                    self._on_item_activated(current)
                return True
        return super().eventFilter(obj, event)




#==============================================================================
# カスタムダイアログクラス: クイックアクセスの管理 (項目87)
#==============================================================================
class QuickAccessManagerDialog(QDialog):
    """
    クイックアクセスツールバーへのピン留めを、チェックボックス付きの検索可能な
    一覧から行うためのダイアログ。CommandPaletteDialogと同様、collect_fn()を
    呼ぶたびに現在有効なメニューアクションを集め直す(表示中に保持したQActionは
    実行には使わない)。

    ★ 注意 ★
    OK/キャンセルの概念を持たない、チェック状態の変更をその場で即座に反映する
    「表示/非表示」に近いトグルUI(閉じるボタンのみ)。
    """

    def __init__(self, collect_fn, is_pinned_fn, toggle_fn, parent=None):
        """
        Args:
            collect_fn (callable): CommandPaletteDialogと同じ契約。呼ぶたびに
                現在のメニューアクションを [(パスのリスト, QAction), ...] として返す。
            is_pinned_fn (callable): (識別子文字列) -> bool。現在ピン留め済みかどうか。
            toggle_fn (callable): (識別子文字列, パスのリスト, チェック後の状態bool) -> None。
                チェック状態が変わった項目に対して呼ばれる、ピン留め/解除の実処理。
        """
        super().__init__(parent)
        from core.i18n import tr

        self.setWindowTitle(tr("クイックアクセスの管理"))
        self.resize(480, 420)

        self._collect_fn = collect_fn
        self._is_pinned_fn = is_pinned_fn
        self._toggle_fn = toggle_fn
        self._updating = False  # _update_list() でのチェック状態初期化中はitemChangedを無視する

        layout = QVBoxLayout(self)

        info_label = QLabel(tr("チェックした項目がクイックアクセスツールバーに表示されます。"))
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(tr("コマンドを検索..."))
        layout.addWidget(self.search_edit)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        self.search_edit.textChanged.connect(self._update_list)
        self.list_widget.itemChanged.connect(self._on_item_changed)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.accept)  # Closeボタンは RejectRole → rejected() を発行する
        layout.addWidget(button_box)

        self._update_list("")

    def _update_list(self, text):
        query = text.strip().lower()
        self._updating = True
        try:
            self.list_widget.clear()
            for path, action in self._collect_fn():
                if action.isSeparator():
                    continue
                label = " > ".join(path)
                if query and query not in label.lower():
                    continue
                ident = " > ".join(path)
                item = QListWidgetItem(label)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setData(Qt.ItemDataRole.UserRole, (ident, path))
                item.setCheckState(
                    Qt.CheckState.Checked if self._is_pinned_fn(ident) else Qt.CheckState.Unchecked
                )
                self.list_widget.addItem(item)
        finally:
            self._updating = False

    def _on_item_changed(self, item):
        if self._updating:
            return
        ident, path = item.data(Qt.ItemDataRole.UserRole)
        checked = item.checkState() == Qt.CheckState.Checked
        self._toggle_fn(ident, path, checked)




#==============================================================================
# カスタムダイアログクラス: 自動バックアップ履歴(項目C-107)
#==============================================================================
class AutosaveHistoryDialog(QDialog):
    """
    既存のオートセーブ世代ローテーション(main_window.pyの
    _rotate_autosave_generations、autosave.graphica/.1./.2.…)の各世代を
    一覧表示し、選んだ世代のパスを返すダイアログ。実際の復元処理
    (_load_project_from_path)は呼び出し側が行う。
    """

    def __init__(self, generations, parent=None):
        """
        Args:
            generations (list[tuple[str, str, str]]): (ファイルパス, 世代ラベル,
                更新日時の文字列)のリスト、新しい順。
        """
        super().__init__(parent)
        self.setWindowTitle("自動バックアップ履歴")
        self.resize(480, 320)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("復元する世代を選んでください(現在の未保存の変更は失われます):"))

        self.history_list = QListWidget()
        for path, label, mtime_text in generations:
            item = QListWidgetItem(f"{label} — {mtime_text}")
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.history_list.addItem(item)
        self.history_list.itemDoubleClicked.connect(self._on_double_clicked)
        layout.addWidget(self.history_list)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(False)
        self.history_list.currentItemChanged.connect(
            lambda current, _previous: self.ok_button.setEnabled(current is not None)
        )
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def _on_double_clicked(self, item):
        self.history_list.setCurrentItem(item)
        self.accept()

    def get_selected_path(self):
        """Returns: str | None (選択されていなければNone)"""
        item = self.history_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None




class PluginParamDialog(QDialog):
    """
    register_processor()/register_analyzer() の param_schema から、パラメータ
    入力フォームを自動生成するダイアログ(項目C-1/C-2)。

    param_schema は dict のリストで、各要素は少なくとも "name" と "type" を持つ:
        {"name": str, "label": str(省略時はname), "type": "int"|"float"|"str"|"bool"|"choice",
         "default": 任意, "min"/"max": int|float(int/floatのみ), "choices": list(choiceのみ),
         "decimals": int(floatのみ、省略時4)}
    """

    _INT_RANGE = (-2_147_483_647, 2_147_483_647)  # Qt QSpinBoxのネイティブ範囲に合わせる

    def __init__(self, title, param_schema, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._widgets = {}  # name -> (type, widget)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        for spec in param_schema:
            name = spec["name"]
            label = spec.get("label", name)
            ptype = spec.get("type", "str")
            default = spec.get("default")
            widget = self._build_widget(ptype, spec, default)
            self._widgets[name] = (ptype, widget)
            form.addRow(label, widget)
        layout.addLayout(form)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        apply_form_spacing(self)

    def _build_widget(self, ptype, spec, default):
        if ptype == "int":
            widget = QSpinBox()
            widget.setRange(spec.get("min", self._INT_RANGE[0]), spec.get("max", self._INT_RANGE[1]))
            widget.setValue(int(default) if default is not None else 0)
            return widget
        if ptype == "float":
            widget = QDoubleSpinBox()
            widget.setDecimals(spec.get("decimals", 4))
            widget.setRange(spec.get("min", -1e12), spec.get("max", 1e12))
            widget.setValue(float(default) if default is not None else 0.0)
            return widget
        if ptype == "bool":
            widget = QCheckBox()
            widget.setChecked(bool(default))
            return widget
        if ptype == "choice":
            widget = QComboBox()
            widget.addItems([str(c) for c in spec.get("choices", [])])
            if default is not None:
                widget.setCurrentText(str(default))
            return widget
        # "str" および未知のtypeはテキスト入力にフォールバックする
        widget = QLineEdit()
        if default is not None:
            widget.setText(str(default))
        return widget

    def get_values(self):
        """Returns: dict {パラメータ名: 入力値(型はparam_schemaのtypeに従う)}"""
        values = {}
        for name, (ptype, widget) in self._widgets.items():
            if ptype in ("int", "float"):
                values[name] = widget.value()
            elif ptype == "bool":
                values[name] = widget.isChecked()
            elif ptype == "choice":
                values[name] = widget.currentText()
            else:
                values[name] = widget.text()
        return values
