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
