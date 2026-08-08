# GUIモダン化(トラック2、フェーズH) 進捗管理

`Graphica_MASTER_SCHEDULE.md` のトラック2(GUIモダン化)の進捗を記録する。
トラック1(プラグインAPI拡張)の進捗は`docs/PLUGIN_API_PROGRESS.md`を参照
(役割は同じ、対象トラックが異なるだけ)。「今どこまで進んでいて次に何を
やるか」の短い要約は`CURRENT_STATE.md`を先に見ること。このファイルは項目が
完了するたびに追記していく(上書きしない)。

**着手条件**: フェーズA〜G(トラック1)が全て完了していること。**達成
(2026-08-07、トラック1完了)**。H-0のみ先行着手可という例外規定だったが、
今回は既にトラック1完了後の着手のため関係なし。

**ブランチ**: `feature/gui-modernization`(`feature/format-version-and-foundations`
から分岐。ロードマップ側の推奨に従い、プラグインAPI拡張とは別PRにする)。

## フェーズH: GUIモダン化(QSSカスタマイズ)

| ID | 項目 | 状態 | 完了日 | 備考 |
|---|---|---|---|---|
| H-0 | 現状把握 | ✅ 完了 | 2026-08-07 | `docs/gui_style_audit.md`新設。QSS/パレット実装は`gui/theme.py`1ファイルに集約(別`.qss`ファイルは無し)、ダーク/ライト切替はQSS+QPalette併用。**重要な発見**: matplotlib側の配色(`gui/canvas.py`)とミニマップ(`gui/minimap_widget.py`)は、`gui/theme.py`のトークンとは完全に独立した、それぞれ個別にハードコードされた`DARK_*`/`LIGHT_*`定数を持つ(値も不一致、統合するかは今後要判断)。レイアウトエディタのドラッグハンドル(#85)はQtウィジェットでもmatplotlib artistでもない、マウスイベント駆動の`ax.set_position()`直接操作(可視インジケータ自体が存在しない)。「カスタムカラーパレット機能」(QSettings)はデータセット線色サイクルであり、UIテーマのアクセントカラーとは無関係と判明(H-1の完了条件にある「関係整理」は「現状は上書き元が無いので対応不要」という結論) |
| H-1 | デザイントークンの整理 | ✅ 完了 | 2026-08-07 | `gui/theme.py`の`_LIGHT_TOKENS`/`_DARK_TOKENS`(既に存在していた)を公開名`LIGHT_TOKENS`/`DARK_TOKENS`にリネームし、`_build_flat_qss(dark: bool)`を`build_qss(tokens: dict)`という公開関数に変更(ロードマップのシグネチャ通り)。`apply_theme()`はこの2つを経由するようリファクタ。**全面書き直しはせず、既存のトークン的構造を公開API化する最小限の整理に留めた**(diff はリネームのみ、値・ロジックは無変更につき視覚的な回帰は原理的に発生しない)。`gui/canvas.py`・`gui/minimap_widget.py`の独自定数は今回統合しない(H-0の所見の通り、意図的な差か単なるズレか切り分けが必要なため、明示的にスコープ外とした) |

**フェーズH-0/H-1完了条件**: 上記2項目が✅。**達成(2026-08-07)**。H-2(コンポーネント単位の磨き込み)に着手可能。

## フェーズH-2: コンポーネント単位の磨き込み(推奨着手順1〜8のうち順に実施)

| ID | 項目 | 状態 | 完了日 | 備考 |
|---|---|---|---|---|
| H-2-1 | メインツールバー・メニューバー | ✅ 完了 | 2026-08-07 | `gui/mixins/quick_access_mixin.py`の`_create_quick_access_toolbar()`に`toolbar.setMovable(False)`を追加。Qt標準ツールバーの移動グリップ(ドラッグ用ハンドル)が、上部固定・移動機能未提供のこのアプリのフラット/ミニマルテーマと視覚的に馴染んでいなかったため除去。実際に`window.grab()`でBefore/Afterスクリーンショット(ライト/ダーク)を撮って確認し、`docs/gui_style_audit.md`のH-2-1節に記録(`docs/screenshots/h2-1/`配下にPNG)。メニューバー自体(QMenuBar/QMenu)はH-1完了時点で既に十分なQSSカバレッジがあり、追加変更なし。`tests/test_quick_access_mixin.py::test_quick_access_toolbar_is_not_movable`を追加 |
| H-2-2 | データセットリスト・データテーブル | ✅ 完了 | 2026-08-08 | `gui/theme.py`に`selection_highlight`トークン(薄い青、透過あり)を新設し、従来の濃いアクセント色塗りつぶしを置き換え。選択ハイライトの形状はQSSの`::item:selected`だけでは(アイコン列とテキスト列が別矩形で描画されるQtの制約により)単一の角丸矩形にできないことが実機検証で判明したため、専用の`_DatasetTreeSelectionDelegate`(`gui/main_window.py`)を新設して自前描画に切り替え、リスト自体の角丸(8px)と揃えた。分岐(展開矢印)用インデント列への汎用スタイルの滲み出しは`background: transparent`で打ち消し、デリゲートの矩形の左端をビューポート0まで伸ばして隙間を解消。検索ボックス・リストそれぞれの枠線(`border: none`)も個別に消したが、**統合はせず独立した箱のまま**、間隔は実機フィードバックを受けて4px→6pxに拡大。`tests/test_theme.py`・`tests/test_main_window.py`にテスト追加、`docs/gui_style_audit.md`のH-2-2節にBefore/After記録(`docs/screenshots/h2-2/`) |
| H-2-3 | ドック全般 | ✅ 完了 | 2026-08-08 | `QDockWidget`に枠線+角丸(8px、`plot_container`と同じ考え方)を追加。フォーカス時の強調は、QDockWidget自体に「アクティブ」を示すQt標準の状態が無いため、新設の`theme.install_dock_focus_highlight(window)`が`QApplication.focusChanged`を監視し、フォーカスされたウィジェットの祖先からQDockWidgetを特定して動的プロパティ`dockActive`を付け外しする自前実装で対応(QSS側は`QDockWidget[dockActive="true"]`の属性セレクタで枠線をアクセント色に)。複数タブ(各PlotterAppタブが完全に独立したウィンドウという設計方針)を踏まえ、見つかったドックが管轄`window`のものでない場合は無視するガードを実装。`undo_history_dock`は`MainAppWindow`自身が持つドックのため、`gui/main_window.py`側とは別に`gui/main_app_window.py`側でも個別に組み込んだ。`tests/test_theme.py`(QSS検証+`TestDockFocusHighlight`4パターン)・`tests/test_main_window.py`・`tests/test_main_app_window.py`にテスト追加、`docs/gui_style_audit.md`のH-2-3節にBefore/After記録(`docs/screenshots/h2-3/`) |
| H-2-4 | ボタン・入力フィールド・コンボボックス | ✅ 完了 | 2026-08-08 | 実機フィードバックによる複数回の調整。(1) スピンボックスの上下ボタンを、フィールド右端に直接くっついた「外側の角だけ丸い帯」から、それぞれ独立した角丸ボックス(参考イメージ提示を受けて全4隅を丸め、margin付き)に変更。さらに背景・枠線を常時透明にし矢印だけが浮くミニマルな見た目に。(2) 矢印マーク(`_spinbox_arrow_icon_url()`で生成するPNG)自体の三角形サイズを拡大、キャッシュファイル名にサイズを含めて旧サイズの使い回しを防止。コンボボックス側の矢印サイズがスピンボックスと揃っていなかった不具合(実機フィードバックで発覚)も12pxに統一して解消。(3) テキスト選択・メニュー/メニューバーの`::item:selected`・コンボボックスのポップアップ・汎用リスト/テーブルの`::item:selected`を、いずれもティール系`accent`/`accent_soft`からH-2-2で導入した青の`selection_highlight`に統一(「選択時とかポップアップの色が緑っぽい」との指摘に対応)。ボタンのhover/pressedやフォーカス枠は`accent`のまま変更なし。(4) `ui_main_window.py`(Designer生成物、手で編集しない方針)に焼き込まれたフォームラベルの末尾全角コロン「：」を、`PlotterApp.__init__`最後で`_strip_trailing_colon_from_labels()`により実行時に除去。`tests/test_theme.py`・`tests/test_main_window.py`にテスト追加、`docs/gui_style_audit.md`のH-2-4節にBefore/After記録(`docs/screenshots/h2-4/`) |
| H-2-4追加分 | (同日追加の実機フィードバック反映) | ✅ 完了 | 2026-08-08 | (1) フォーカス/選択/チェック状態の色をすべて新設`selection_accent`(opaqueな青)に統一: ボタン/入力欄の`:focus`枠線、`QDockWidget[dockActive="true"]`(H-2-3)の枠線、`QTabBar::tab:selected`の下線・文字色、`QRadioButton::indicator:checked`、チェックボックスのチェック時塗りつぶし(`_draw_checkbox_indicator`)。ブランドアクセントとしての`accent`自体(ボタン背景等)は変更なし。(2) プロパティドックの余計な枠線は`QScrollArea`に一切QSSが無くQt既定のsunkenフレームが出ていたのが原因と判明、`QScrollArea { border: none; }`で解消(エクスポートプレビューはQScrollAreaでラップされておらず、両者の見た目が不揃いだった)。(3) 背景色`bg`/`surface_2`を「若干黄色っぽい」との指摘を受け、3案提示の上で選ばれた寒色寄りグレー(`bg=#F6F7F9`, `surface_2=#EEF0F3`)に変更。(4) タイトル/軸ラベル編集を、以前のQMenuベースのポップアップパネルから、レイアウト画像で提示された独立ポップアップダイアログ`LabelEditDialog`(`gui/dialogs.py`)に置き換え。太字/イタリック/上付き/下付きの装飾ボタンを常時見える横一列(`QPushButton[iconOnly="true"]`)にし、Ωのギリシャ文字/記号パレット(`LABEL_SYMBOL_PALETTE`)は「四則演算の記号とかプロットでよく使う数学記号があるといいかも」との要望を受けてギリシャ文字16種+算術・数学記号16種の計32種に拡張(matplotlib mathtextで実際に解釈可能なマクロのみ収録、テストで確認済み)。`gui/mixins/settings_mixin.py`の旧`_capture_label_format_selection`/`_apply_label_mathtext_format`/`_on_label_*_clicked`系メソッド、`gui/mixins/ui_setup_mixin.py`の対応する配線は不要になったため削除。`tests/test_theme.py`・`tests/test_main_window.py`・`tests/test_dialogs.py`にテスト追加、`docs/gui_style_audit.md`のH-2-4追加分節にBefore/After記録(`docs/screenshots/h2-4/`) |
| H-2-4追加分(続き) | 同日さらに続いた実機フィードバック5件の反映 | ✅ 完了 | 2026-08-08 | (1) `QDockWidget`に`background: {bg};`が無くOSネイティブパレット色が透けていたのが「プロパティウィンドウの背景色がそのまま」の真因と判明、追加して解消。(2) `LabelEditDialog`のB/I/x²/x₂/Ωボタンが`QPushButton.clicked`(フォーカス移動後に発火)経由で選択状態を見ていたため「選択後にボタンを押すと未選択と言われる」バグが再発、過去にも踏んだ「`pressed`シグナルで選択範囲を先に捕捉する」パターンで解消(`_capture_pending_selection`を4ボタン+Ωボタンの`pressed`に接続)。(3)+(4) タイトル/軸ラベルの入力欄自体をクリックしたら`LabelEditDialog`が開くよう変更、かつその入力欄にmathtextの実描画結果をライブプレビュー表示するよう変更。既存`QLineEdit`は非表示のままデータ保持・シグナル配線用に温存し、新規`_ClickableMathPreviewLabel`(`gui/main_window.py`)を可視/クリック可能な代替として`formLayout_3`に`replaceWidget`。プレビュー描画は新規`gui/mathtext_preview.py`(`matplotlib.figure.Figure`+`FigureCanvasAgg`で描画しアルファ>0範囲をクロップ)。matplotlib既定フォント(DejaVu Sans)に日本語グリフが無くプレースホルダ/日本語タイトルがtofuボックスになる不具合が発覚し、`family=["DejaVu Sans","Yu Gothic","Meiryo","MS Gothic"]`のフォールバックリストで解消(ただし`"$\alpha$ vs 時間"`のようにmathtext記法と日本語が同一文字列に混在するケースは、mathtextパーサがfamily指定を経由しない別のフォント解決経路を使うため未解消のまま残存。`gui/canvas.py`の実プロット描画も同じ制約を持つアプリ全体の既存の限界であり、`mathtext.fontset`(matplotlibのグローバルrcParams)の変更を伴うためスコープ外として明示的に見送った、既知の残課題)。ダークモード切替時の再レンダリングは`_on_toggle_dark_mode`から`_refresh_all_label_previews()`を呼んで対応、汎用アクセサ`theme.current_tokens()`を新設。(5) `QPushButton:hover`の`border-color`だけ`{accent}`(ティール)のまま更新漏れだったのを`{selection_accent}`に統一。`tests/test_mathtext_preview.py`(新規)・`tests/test_theme.py`・`tests/test_main_window.py`にテスト追加、`docs/screenshots/h2-4/after_dock_bg_and_preview_*.png`等にBefore/After記録 |

### H-2-5〜H-2-8、H-3〜H-5

未着手。詳細は`Graphica_ROADMAP_PLUGIN_AND_GUI.md`のH-2節以降(推奨着手順5〜8)を参照。

---

## 更新履歴

- 2026-08-07: 新規作成。H-0・H-1完了を反映。
- 2026-08-07: H-2-1(メインツールバー・メニューバー)完了を反映。
- 2026-08-08: H-2-2(データセットリスト・データテーブル)完了を反映。
- 2026-08-08: H-2-3(ドック全般)・H-2-4(ボタン・入力フィールド・コンボボックス)完了を反映。
