# GUIスタイル現状調査(項目H-0)+ コンポーネント磨き込みBefore/After(項目H-2)

トラック2(GUIモダン化、フェーズH)着手にあたっての現状調査(H-0、事実の記録)と、
H-2「コンポーネント単位の磨き込み」で実施した変更ごとのBefore/Afterスクリーン
ショット記録をまとめたドキュメント。H-1〜H-5はH-0の調査結果を土台に進める。

## 1. QSS/パレットの実装場所

**別ファイルの`.qss`は存在しない。** 全て`gui/theme.py`(1ファイル、749行)に
Pythonコードとして実装されている。

- `_LIGHT_TOKENS` / `_DARK_TOKENS`(モジュール非公開の辞書): `bg`/`surface`/
  `surface_2`/`border`/`border_strong`/`text_primary`/`text_secondary`/
  `text_muted`/`accent`/`accent_soft`/`accent_text`の11キーを持つ、ニュートラル
  グレー+ティール系アクセントの配色トークン。**H-1が要求する「一箇所の辞書」は
  実質的に既に存在している**(公開名への変更・別ファイルへの切り出しの余地はあるが、
  ゼロから作る必要はない)。
- `_FLAT_QSS_TEMPLATE`: 上記トークンを`{token_name}`プレースホルダとして埋め込んだ、
  Python `str.format(**tokens)`方式のQSS文字列(H-1の完了条件で言及されている
  `.qss.tpl`ファイル+プレースホルダ置換という設計は、ファイルこそ分かれていないが
  仕組みとしては既に採用済み)。メニューバー・ツールバー・ドック・グループボックス・
  入力欄・リスト/ツリー/テーブル・タブ・スクロールバー等、主要なQt標準ウィジェットを
  一通りカバーしている。
- `_build_dark_palette()`: `QPalette`ベースの色(`Window`/`Base`/`Text`/`Button`/
  `Highlight`等)を個別に構築。QSSではカバーしきれない、ネイティブ描画に近い部分
  (選択ハイライト等)を担当。
- `_FlatThemeProxyStyle(QProxyStyle)`: QSSだけでは実現できない(むしろ壊れる)
  2箇所を自前描画で肩代わりする専用スタイル。詳細はコード内コメントに詳しいが、
  **Qtの既知の癖として明記されている**: `QCheckBox::indicator`や
  `QTabBar::close-button`に何か1つでもQSSプロパティ(padding/border-radius等)を
  指定すると、Qtがそのサブコントロールを「スタイルシートでカスタム描画される」
  ものとみなし、中身(チェックマーク/アイコン)を一切描画しなくなる。そのため
  チェックボックスの枠・塗り・チェックマーク、タブの閉じるボタンアイコンは
  QSSを一切使わず`drawPrimitive`/`standardIcon`/`standardPixmap`で直接描画している。
  **H-2以降でチェックボックスやタブに触れる際は、この制約を必ず踏襲すること。**
- `apply_theme(app, dark: bool)`: 上記3つ(パレット・QSS・ProxyStyle)を束ねる
  唯一の公開エントリポイント。スタイル自体は常に`Fusion`固定(ネイティブ⇔Fusion
  切り替えはしない。切り替えるとツールバーサイズ等がモードごとに変わってしまう
  ため、と明記されている)。

## 2. ダーク/ライト切り替えの仕組み

**QSS切り替えとパレット切り替えの併用。** `apply_theme()`が両方を同時に適用する。
切り替えの起点は`gui/mixins/ui_setup_mixin.py`の「表示」メニュー内
`dark_mode_action`(チェック可能なQAction)で、`gui/mixins/project_io_mixin.py`
経由でQSettingsの`dark_mode`キーに永続化される。

## 3. matplotlib側の配色とダークモードの連動

**トークンとは完全に独立した、個別のハードコード定数で連動している。**
`rcParams`経由ではなく、`Dataset`側のスタイル設定経由でもない。`gui/canvas.py`
(`MplCanvas`)は`self.dark_mode`という独自の真偽値属性を持ち(`main_window`から
都度設定される)、モジュール冒頭に以下の定数を個別に定義して、描画のたびに
`X if self.dark_mode else Y`という条件分岐で参照している:

```python
DARK_FIGURE_FACECOLOR = '#2b2b2b'   LIGHT_FIGURE_FACECOLOR = '#ffffff'
DARK_AXES_FACECOLOR   = '#1e1e1e'   LIGHT_AXES_FACECOLOR   = '#ffffff'
DARK_TEXT_COLOR       = '#e0e0e0'   LIGHT_TEXT_COLOR       = '#000000'
DARK_LEGEND_FACECOLOR = '#2A2A2A'   LIGHT_LEGEND_FACECOLOR = '#FFFFFF'
DARK_LEGEND_EDGECOLOR = '#4A4A4A'   LIGHT_LEGEND_EDGECOLOR = '#CCCCCC'
```

`gui/theme.py`の`_DARK_TOKENS["bg"]`(`#14171A`)等とは値が一致しておらず、
参照関係も無い。**Qt側のテーマとmatplotlib側の配色は、今のところ「別々に
存在する2つのダークモード実装」である。**

### 重複その2: `gui/minimap_widget.py`

ミニマップ(項目#83)は上記と全く同じパターン(`self.dark_mode`属性 +
`DARK_*`/`LIGHT_*`モジュール定数 + 条件分岐)を、`gui/canvas.py`とは別の値で
**独立に**再実装している:

```python
DARK_FIGURE_FACECOLOR = '#2b2b2b'   LIGHT_FIGURE_FACECOLOR = '#ffffff'
DARK_AXES_FACECOLOR   = '#1e1e1e'   LIGHT_AXES_FACECOLOR   = '#f2f2f2'
DARK_LINE_COLOR       = '#8ab4f8'   LIGHT_LINE_COLOR       = '#1a73e8'
DARK_SPAN_COLOR       = '#8ab4f8'   LIGHT_SPAN_COLOR       = '#1a73e8'
```

`gui/`配下を`DARK_*`/`LIGHT_*`命名パターンで横断検索した結果、この2ファイル
(`canvas.py`・`minimap_widget.py`)以外にこのパターンの重複は無いことを確認済み。

### `ExportPreviewPanel`は独自定数を持たない

`gui/export_preview_panel.py`はエクスポート用の一時`MplCanvas`を生成する際に
`temp_canvas.dark_mode = mw.canvas.dark_mode`とメイン画面の状態をそのまま
コピーしているだけで、独自の配色定数は持たない(プレビュー画像は常に
現在のアプリのモードに追従する。透過背景オプションは保存/コピー時のみ適用され、
画面プレビュー自体は常に不透明)。

## 4. カスタムウィジェット一覧

| ウィジェット | ファイル | スタイリング方式 | ダークモード対応 |
|---|---|---|---|
| ドック各種(プロパティ/エクスポートプレビュー/プラグインパネル) | `gui/main_window.py` | `gui/theme.py`のQSS(`QDockWidget::title`等)に一任 | Qt側のみ(theme.py経由)、個別対応なし |
| クイックアクセスツールバー(#87) | `gui/mixins/quick_access_mixin.py` | `QToolBar`+既存メニューの`QAction`を再利用するのみ。インラインスタイル・独自色は皆無 | 個別対応なし(theme.py経由のみ) |
| 色ピッカー(`ColorPickerWidget`) | `gui/color_picker_widget.py` | スウォッチボタンに**インラインの`setStyleSheet()`**を使用: `background-color: {現在の色}; border: 1px solid rgba(128,128,128,110); border-radius: 4px;`。この`rgba(128,128,128,110)`という枠線色は`gui/theme.py`のトークンから来ておらず、個別にハードコードされている | 枠線色は固定(グレー半透明)でモード非依存。スウォッチの背景色自体はユーザーが選んだデータ色なのでモードとは無関係 |
| レイアウトエディタのドラッグハンドル(#85) | `gui/mixins/layout_edit_mixin.py` | **Qtウィジェットではなくmatplotlibイベント駆動**。`canvas.mpl_connect('button_press_event'等)`で拾ったマウス座標を`ax.bbox`と直接比較するヒットテストのみで、専用の描画コード・可視インジケータは存在しない(選択中の判定はスピンボックス側UIの同期のみで表現)。QtのQSSともmatplotlibの配色定数とも無関係な第三のカテゴリ | 該当なし(視覚要素そのものが無い) |
| ミニマップ(#83) | `gui/minimap_widget.py` | 独自の`DARK_*`/`LIGHT_*`定数(上記3節参照) | あり(ただしcanvas.pyと重複・不整合) |
| エクスポートプレビューパネル | `gui/export_preview_panel.py` | `gui/theme.py`の`apply_form_spacing()`を呼ぶのみ。独自スタイルなし | メインキャンバスの`dark_mode`をそのままコピー(3節参照) |
| コマンドパレット(#47、`CommandPaletteDialog`) | `gui/dialogs.py` | `QLineEdit`+`QListWidget`のみ、インラインスタイルなし。チェック可能項目は`✓`をテキストに直接埋め込み(アイコン/QCheckBoxは不使用) | 個別対応なし(theme.py経由のみ)。`QuickAccessManagerDialog`も同一パターン |

## 5. アイコンの配色(`gui/icon_utils.py`)

Tabler IconsのSVG(`stroke="currentColor"`)を`color`引数で塗り替えて`QIcon`化する
仕組み(`icon(name, color=DEFAULT_ICON_COLOR, size=16)`)。`DEFAULT_ICON_COLOR =
"#3B3F42"`という**固定のダークグレー**が既定値で、呼び出し側の多くはこの既定値を
そのまま使っている。**ダークモード時にこの固定色がどう見えるかは今回未検証**
(暗い背景に暗いグレーのアイコンではコントラストが低くなる可能性がある。
H-2/H-3でアイコンに触れる際に併せて確認する価値がある、という所見のみ記録)。

## 6.「カスタムカラーパレット」機能との関係整理

ロードマップH-1の完了条件に「既存のカスタムカラーパレット機能(QSettingsに
永続化)との関係を整理する」とあるが、**調査の結果、これはUIテーマのアクセント
カラーとは無関係の別機能である**ことを確認した:

- `ColorPaletteDialog`(`gui/dialogs.py`)・`COLOR_PALETTES_SETTINGS_KEY`
  (`gui/mixins/dataset_mixin.py`)は、「自動配色」ボタンで使う**データセットの
  線色サイクル**(matplotlibのcolor cycleに相当)をユーザーが複数定義・切り替え
  られる機能であり、アプリのUIクロム(メニューバー・ボタン等)の配色とは
  無関係。
- `gui/color_history.py`は色ピッカーの「最近使った色」履歴(QSettings保存)で、
  これもUIテーマとは無関係。
- **アプリのUIテーマのアクセントカラー(`gui/theme.py`の`accent`/`accent_soft`/
  `accent_text`)をユーザーがカスタマイズできる機能は現状存在しない**
  (ハードコードされた固定値のみ)。

したがって、H-1で`tokens["color.primary"]`をユーザー設定で上書きできるように
という完了条件の一文は、**現状は上書き元となる既存のユーザー設定が無い**ため、
「今は考慮不要、必要になれば新規に設計する」という結論になる。上記2つの既存の
QSettings機能と衝突・混同しないよう、命名(トークンのキー名など)だけ注意すれば
十分。

## 7. H-1以降への申し送り事項

1. `_LIGHT_TOKENS`/`_DARK_TOKENS`は既にある。H-1は「ゼロから作る」のではなく
   「公開API化する/必要なキーを追加する/`gui/canvas.py`・
   `gui/minimap_widget.py`の重複した独自定数をこのトークン経由に一本化する」
   というリファクタが実体になる。
2. `gui/canvas.py`と`gui/minimap_widget.py`のダーク/ライト配色定数は、値が
   微妙に異なる(例: axes facecolor、`#1e1e1e`/`#ffffff` vs `#1e1e1e`/`#f2f2f2`)
   独立した重複。統合する際は「意図的な差」なのか「単なる書き忘れによるズレ」
   なのか切り分けが必要(今回は現状記録のみで判断しない)。
3. `_FlatThemeProxyStyle`のチェックボックス/タブ閉じるボタンの自前描画は、
   Qtの実機検証済みの制約に基づく必須の回避策。トークンをリファクタする際も
   この2箇所はQSSに戻さないこと。
4. `ColorPickerWidget`のスウォッチ枠線色のような、個別ウィジェットに埋め込まれた
   インラインの`setStyleSheet()`が他にも存在する可能性がある(今回はH-0の
   スコープで确認した範囲のみ記録。H-2のコンポーネント単位の磨き込みで
   横断的に洗い出す余地がある)。
5. アイコンの固定色(`DEFAULT_ICON_COLOR`)がダークモードでどう見えるかは
   要確認(上記5節)。

---

## H-2-1. メインツールバー・メニューバー

**変更内容**: `gui/mixins/quick_access_mixin.py`の`_create_quick_access_toolbar()`で
`toolbar.setMovable(False)`を追加。

**理由**: Qt標準の`QToolBar`は既定でユーザーがドラッグして再配置・フローティング化
できる「移動グリップ」(ツールバー左端のドット状のハンドル)を描画する。この
アプリでは上部に固定された単一のツールバーのみを想定しており(#87 クイックアクセス
ツールバー)、ユーザーが動かす機能は提供していないため、このグリップは
「動かせそうに見えるが実際には特別な意味を持たない」不要な視覚要素になっていた。
QSSではこのグリップ自体を隠すことはできない(Qt標準の`QStyle`描画の一部)ため、
`setMovable(False)`でQtの標準機能として無効化した(移動不可にすればグリップも
描画されなくなる)。フラット/ミニマルテーマの一貫性を高める、H-0の調査後に
実際にスクリーンショットを見て気づいた具体的な改善点。

**Before/After**(ライトモード):

| Before | After |
|---|---|
| ![Before(ライト)](screenshots/h2-1/before_light.png) | ![After(ライト)](screenshots/h2-1/after_light.png) |

**Before/After**(ダークモード):

| Before | After |
|---|---|
| ![Before(ダーク)](screenshots/h2-1/before_dark.png) | ![After(ダーク)](screenshots/h2-1/after_dark.png) |

ツールバー左端の「::::」状のドラッグハンドルが消え、テキストがそのまま左端から
始まるようになった。メニューバー自体(ファイル/編集/表示/プラグイン/ヘルプ)は
H-1時点で既に`gui/theme.py`のQSS(`QMenuBar`/`QMenu`セクション)でカバー済み
であり、今回追加の変更は無し(H-0調査の通り、丸角・ホバー時のアクセント色強調
などは既に実装されていたため)。

**メニューの開閉状態(参考)**: メニューを開いた際の見た目(`QMenu`のドロップダウン、
ホバー時のアクセント色強調)は既存のQSSで実装済みで、今回変更していない
(角丸8px・ボーダー・ホバー時`accent_soft`背景、`docs/gui_style_audit.md` 1節参照)。

**テスト**: `tests/test_quick_access_mixin.py::test_quick_access_toolbar_is_not_movable`
を追加。既存のUIテスト(オフスクリーン)は全てグリーン。

## H-2-2. データセットリスト・データテーブル

**変更内容**: `gui/theme.py`(選択ハイライトの配色・枠線)と
`gui/main_window.py`(専用アイテムデリゲート・検索ボックスの間隔)の両方に渡る。

1. **選択ハイライトの配色**: `LIGHT_TOKENS`/`DARK_TOKENS`に`selection_highlight`
   トークンを新設(ライト: `rgba(37, 99, 235, 0.12)`、ダーク:
   `rgba(59, 130, 246, 0.22)`)。従来の「はっきりしたアクセント色(ティール系)の
   塗りつぶし」から、透明度を持たせた薄い青に変更した。
2. **選択ハイライトの形状**: `_DatasetTreeSelectionDelegate`
   (`gui/main_window.py`)を新設し、`dataset_list_widget`の`setItemDelegate()`で
   登録。選択時の背景描画をこのデリゲートが自前で行い、アイコン列+テキスト列+
   分岐(展開矢印)用インデント列を含む行全体を、リスト自体の角丸(8px、
   `DATASET_LIST_ITEM_RADIUS`)と揃えた単一の角丸矩形として描画する。
3. **リスト・検索ボックスそれぞれの枠線**: `QTreeWidget#dataset_list_widget`と
   `QLineEdit#dataset_search_edit`(新設objectName)の両方に`border: none;`を
   追加し、灰色の枠線を消した。**リストと検索ボックスを1つの箱に統合するのが
   目的ではない**(実機フィードバックで明確に区別された)ため、両者の間の
   レイアウト間隔(`container_layout.setSpacing()`)はそのまま独立を保っており、
   むしろ実機フィードバックを受けて4px→6px(約1.5倍)に広げている。

**理由・経緯(実機フィードバックによる複数回の調整)**:

- 当初のQSS(`::item:selected { background; border-radius; }`)だけでは、
  選択ハイライトを「アイコン列+テキスト列にまたがる単一の角丸矩形」として
  描画できないことが実機検証で判明した。Qt(Fusionスタイル)は
  `CE_ItemViewItem`の描画時にデコレーション(アイコン)列とテキスト
  (display)列を別々の矩形として扱い、`background`/`border-radius`もそれぞれ
  独立に適用するため、2つの矩形の角丸がわずかにズレて隙間から地の色が
  透けて見えていた。`border-radius: 0`にすれば隙間自体は消えるが、今度は
  リスト自体の角丸(8px)と揃わなくなる。QSSの`show-decoration-selected`
  プロパティで1矩形に統合できないか試したが、PySide6の
  `QTreeView`/`QTreeWidget`にはこのプロパティに対応する公開APIが無く
  (`hasattr()`で確認済み)、QSS指定も実機で効果が無かった。
- 分岐(展開矢印)用インデント列は、`delegate.paint()`とは別の
  `QTreeView::drawBranches()`という独自の経路で描画されており、モデル側の
  実際の選択状態を見るため、汎用のリスト共通スタイル(`accent_soft`を使う
  `QTreeWidget::item:selected`規則)がそのまま滲み出てしまう。このリストに
  限って`background: transparent`で打ち消している。
- デリゲートが描く矩形は当初アイコン+テキスト部分(`opt.rect`)だけで、
  分岐用インデント列の分だけ左端に隙間が空いてしまっていた
  (「ここの隙間空いちゃうのは直せる?」という実機フィードバックで発覚)。
  インデント列は何も描画されない(上記の理由で`transparent`)ため、
  デリゲートの矩形の左端をビューポートの0まで伸ばして埋めても他の描画と
  衝突しないことを確認し、修正した。

**Before/After**(ライトモード):

| Before | After |
|---|---|
| ![Before(ライト)](screenshots/h2-2/before_light.png) | ![After(ライト)](screenshots/h2-2/after_light.png) |

**Before/After**(ダークモード):

| Before | After |
|---|---|
| ![Before(ダーク)](screenshots/h2-2/before_dark.png) | ![After(ダーク)](screenshots/h2-2/after_dark.png) |

選択行が、濃いアクセント色の塗りつぶし(かつ左端に色の異なる箱が独立して
見えていた)から、リストの角丸と揃った単一の薄い青の帯に変わった。検索
ボックス・リストそれぞれの灰色の枠線も消え、間隔だけが独立した箱として
保たれている。

**テスト**: `tests/test_theme.py`に`selection_highlight`トークンの存在、
`current_selection_highlight_qcolor()`のrgba()パース、生成QSSの
`border: none`/`background: transparent`指定を検証するテストを追加。
`tests/test_main_window.py`に、デリゲートが実際に設定されていること・
検索ボックスのobjectName・間隔(6px)・デリゲートのpaint()が例外を出さない
ことを検証するテストを追加。

## H-2-3. ドック全般

**変更内容**: `gui/theme.py`(QDockWidgetの枠線・角丸・フォーカス時強調のQSS)
と、`gui/main_window.py`/`gui/main_app_window.py`(新設の
`theme.install_dock_focus_highlight()`呼び出し)の両方に渡る。

1. **境界線**: `QDockWidget { border: 1px solid {border}; border-radius: 8px; }`
   を追加。以前はタイトルバーの背景色だけが手がかりで、キャンバス周り
   (`plot_container`、1節参照)のような「1枚のカード」として認識しにくかった。
   `QDockWidget::title`にも上端の角丸(`border-top-left-radius`/
   `border-top-right-radius`)を追加し、ドック本体の角丸と揃えている。
2. **タイトルバー**: 既存のQSS(背景・パディング・太字)は変更なし。角丸の
   追加のみ。
3. **フォーカス時の強調**: QDockWidget自体には「アクティブ」を示すQt標準の
   状態が無いため、`theme.install_dock_focus_highlight(window)`を新設し、
   `QApplication.focusChanged`を監視してフォーカスされたウィジェットの祖先を
   たどりQDockWidgetを特定、動的プロパティ`dockActive`をQSSの属性セレクタ
   (`QDockWidget[dockActive="true"]`)経由で反映する。フォーカスが当たった
   ドックの枠線がアクセント色になる。プラグイン製パネル(項目D-1)も祖先を
   たどる方式のため個別登録なしで自動カバーされる。**複数タブ対応の注意点**:
   `focusChanged`はプロセス内全体で共有される単一のシグナルのため、
   見つかったドックが自分の管轄する`window`のものでない場合は無視する
   ガードが必須(各PlotterAppタブは完全に独立したウィンドウという設計方針、
   本ファイル冒頭の注意点参照)。`undo_history_dock`はPlotterApp(各タブ)
   ではなく`MainAppWindow`自身が持つドックのため、`gui/main_window.py`側の
   呼び出しとは別に`gui/main_app_window.py`側でも個別に組み込んでいる。

**Before/After**(ライトモード、上: 非フォーカス時、下: フォーカス時):

| Before | After(非フォーカス) | After(フォーカス) |
|---|---|---|
| ![Before(ライト)](screenshots/h2-3/before_light.png) | ![After非フォーカス(ライト)](screenshots/h2-3/after_resting_light.png) | ![Afterフォーカス(ライト)](screenshots/h2-3/after_focused_light.png) |

**Before/After**(ダークモード):

| Before | After(非フォーカス) | After(フォーカス) |
|---|---|---|
| ![Before(ダーク)](screenshots/h2-3/before_dark.png) | ![After非フォーカス(ダーク)](screenshots/h2-3/after_resting_dark.png) | ![Afterフォーカス(ダーク)](screenshots/h2-3/after_focused_dark.png) |

**テスト**: `tests/test_theme.py`に、生成QSSがQDockWidgetへ枠線・角丸・
`dockActive`属性セレクタを持つことを確認するテストと、
`TestDockFocusHighlight`クラス(フォーカス移動でdockActiveが立つ/外れる、
他ウィンドウのドックには影響しない、ウィンドウ破棄後にハンドラが
disconnectされる、の4パターン)を追加。`tests/test_main_window.py`・
`tests/test_main_app_window.py`にも、それぞれのウィンドウで実際に
`install_dock_focus_highlight()`が呼ばれていることを確認するテストを追加。

## H-2-4. ボタン・入力フィールド・コンボボックス

**変更内容**: 実機フィードバックによる複数回の調整。`gui/theme.py`
(スピンボックス/コンボボックスの矢印・選択色)と`gui/main_window.py`
(フォームラベルの末尾コロン除去)の両方に渡る。

1. **スピンボックスの上下ボタン**: 以前はフィールド右端に直接くっついた
   「外側の角だけ丸い」1つの帯だったが、参考イメージの提示を受け、上下
   それぞれが独立した小さな角丸ボックスに見えるよう全4隅を丸め、marginで
   枠線・フィールドの双方から少し離した。さらに「透明にして枠線も消して」
   との追加フィードバックを受け、ボタン自体の背景・枠線は常時透明にし、
   矢印アイコンだけが浮いて見えるミニマルな見た目に変更(hover/pressed時
   のみ背景色を出す)。
2. **矢印マークのサイズ**: 「もう少し大きく」とのフィードバックを受け、
   矢印画像の生成元(`_spinbox_arrow_icon_url()`)自体の三角形サイズを
   拡大(表示サイズだけを大きくしても、透明パディングの多い元画像を
   ただ引き伸ばすだけで見た目が小さいままだったため、キャンバスサイズ
   ごと見直した)。あわせて、キャッシュファイル名にサイズを含めるよう
   変更し(`spin_arrow_{direction}_{color}_{size}.png`)、寸法変更のたびに
   一時ディレクトリの旧サイズPNGを誤って使い回すことがないようにした。
   **回帰**: スピンボックス側のみ12pxに拡大し、コンボボックスの矢印が
   旧サイズ(10px)のまま揃っていなかった不具合が実機フィードバック
   (「コンボボックスとスピンボックスでマークの大きさそろってる?」)で
   発覚し、12pxに統一した。
3. **選択色をデータセットリストに揃える**: 「選択時とかポップアップとか
   色が緑だからデータセットリストの方に色合わせて」とのフィードバックを
   受け、テキスト選択(`QWidget`の`selection-background-color`)、
   メニュー/メニューバーの`::item:selected`、コンボボックスのポップアップ
   (`QComboBox QAbstractItemView`)、汎用のリスト/テーブルの
   `::item:selected`を、いずれもティール系の`accent`/`accent_soft`から、
   データセットリスト(H-2-2)で導入した薄い青の`selection_highlight`
   トークンに統一した。ボタンのhover/pressedやフォーカス枠など「選択」
   以外のアクセント表現は従来通り`accent`のまま変更していない。
4. **フォームラベルの末尾コロン除去**: 「各設定項目のあとの：はなくして」
   とのフィードバックを受けて対応。`ui_main_window.py`(Qt Designer/
   pyside6-uic生成物)の`retranslateUi()`には、多くのフォームラベルに
   全角コロン「：」(`：`のエスケープ形式で埋め込まれており、リテラル
   文字列としての単純なgrepでは見つからないので注意)が焼き込まれている。
   `.ui`ソースファイル自体がこのリポジトリに存在せず再生成もできないため、
   `PlotterApp.__init__`の最後(全てのラベル構築が終わった後)で
   `_strip_trailing_colon_from_labels()`を呼び、QLabelのtext()を
   走査して末尾の「：」だけを取り除く形で対応した(Designer側の元データは
   変更していない)。

**Before/After**(スピンボックス、ライトモード):

| Before | After |
|---|---|
| ![Before](screenshots/h2-4/before_spinbox_zoom.png) | ![After](screenshots/h2-4/after_combobox_spinbox_zoom.png) |

**After: コンボボックスのポップアップ選択色**:

| ライト | ダーク |
|---|---|
| ![ポップアップ(ライト)](screenshots/h2-4/after_combobox_popup_light.png) | ![ポップアップ(ダーク)](screenshots/h2-4/after_combobox_popup_dark.png) |

**After: フォームラベルのコロン除去**:

| ライト | ダーク |
|---|---|
| ![ラベル(ライト)](screenshots/h2-4/after_labels_no_colon_light.png) | ![ラベル(ダーク)](screenshots/h2-4/after_labels_no_colon_dark.png) |

**テスト**: `tests/test_theme.py`に、選択系プロパティが軒並み
`selection_highlight`を使っていること・旧ティール色がもう使われていない
こと・コンボボックスとスピンボックスの矢印サイズが一致していることを
確認するテストを追加。`tests/test_main_window.py`に
`TestStripTrailingColonFromLabels`クラス(末尾コロンのみ除去・末尾以外の
コロンは残す・実際のPlotterAppのラベルで確認、の3パターン)を追加。
