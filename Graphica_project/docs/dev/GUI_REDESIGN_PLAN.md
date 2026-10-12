# GUI 刷新(Lite / Advanced)

2026-10-12 にユーザーと決めた GUI の作り直し。詳しい計画は `docs/dev/mockups/gui_redesign/plan.html`
(Artifact: https://claude.ai/artifact/VGAQNzNeEMRLCNekTQULjD 。リポジトリのファイルを正とし、変えたら公開し直す)。
見本は `docs/dev/mockups/gui_redesign/final_lite_advanced.html`(ブラウザで開く。ライト/ダーク、Lite/Advanced、
テーマカラーを切り替えられる)。`earlier/` は途中の案で、採用しなかったもの。

## ブランチ

- 統合ブランチ `feature/gui-redesign`。各 PR はここに向け、CI が通ればマージしてよい(macOS 実機の確認が要る PR は確認の後)。
- `feature/gui-redesign` → `master` は、ユーザーが統合ブランチの exe で最終確認し、了承した後だけ。
- `build.yml` の `pull_request.branches` に統合ブランチを足してある。master へマージした後に外す。

## 決まったこと

- 構成: 上部1段(≡・タブ・コマンドを検索・モードの切り替え・元に戻す/やり直す・保存・エクスポート)、左端のアイコンの帯、
  左にデータセット、中央にグラフのカード、右にインスペクタ(プロパティ・軸・凡例・エクスポートのタブ)、Advanced だけグラフの下にパネル。
- Lite と Advanced は同じ画面で、Advanced は部品が足されるだけ。例外はグラフの道具(Lite は左に縦のアイコン、
  Advanced はプロットの上に文字付き)と、グラフの種類(Lite はアイコン4択、Advanced は「種別」のコンボ)。
- 部品は1組だけ作り、モードで表示を出し分ける。今の部品(コンボ・チェックボックス・スピンボックス)を値の持ち主として残し、
  データの対応表(`DATASET_PROPERTY_BINDINGS`・`AXIS_BINDINGS`)を壊さない。モードの切り替えで値は変わらない。
- テーマカラーは利用者が選べる。既定はアイコンの背景色 `#0F4C5C`。選んだ1色から、明るさだけを動かして背景とのコントラスト比
  4.5 以上(ダークの文字色は 7 以上)にした色を使う。設定には選んだ色だけを保存する。グラフの線の色とエクスポートは変わらない。
- 保存形式(`.gra`)は変えない。プラグイン API も変えない(`register_panel` のパネルは帯の「プラグイン」のページに入る)。

細部(計画の「9. 決めたこと」、すべて推奨どおり):

1. 既定のモードは、初めて起動した人は Lite、今の利用者(`has_shown_welcome` が真)は Advanced。
2. 表示名は日本語「シンプル / アドバンスド」、英語 Lite / Advanced(2026-10-12 にユーザーが「詳細」から変更)。
3. クイックアクセスは上部バーの「元に戻す・やり直す」の右にアイコンで。
4. Windows はメニューを ≡ にまとめ、macOS はネイティブのメニューバーも残す。
5. 左・右・下のパネルは固定。ドックレイアウトのプリセット機能はやめる。キャンバスの切り離しは残す。
6. 帯の「解析」「注釈」「レイアウト」のページは、まず今の操作へのボタンの並び。作り込みは刷新の後。
7. Lite の「線+点」は種類 Line のまま、マーカーが無ければ「円」。
8. グラフのカードのタイトルは選んでいるサブプロットのタイトル。無ければ「サブプロット N」。
9. 見た目・配置を意図して変えるコミットでは特性テストのゴールデンを作り直してよい(作り直しのコミットを分け、本文に理由)。
10. ツールバーの統計ボタンとミニ統計のラベルは無くし、左パネルの統計カードにする。
11. 残差プロットのドックは、下のパネルのタブ「残差」にする。

外したもの: プロパティのピン(固定)、表形式のプロパティグリッド、密度の切り替え。

## PR の順番

0. 見本と計画の取り込み(この文書)
1. テーマの土台(トークン・テーマカラーの計算・QPalette・設定。配置は変えない)
2. 新しい部品(`gui/widgets/`)
3. 画面の骨組みとモードの仕組み(上部バー・帯・左パネルの入れ物・`gui/ui_mode.py`)— macOS 実機の確認
4. 左パネル(データセット)とプラグインのページ
5. グラフのカード
6. インスペクタ
7. 下のパネル(Advanced)
8. ステータスバーと ⚙ の設定
9. 仕上げ(英語・スクリーンショット・CHANGELOG・Wiki)— macOS 実機の確認、その後ユーザーの最終確認

各 PR の触るファイル・テスト・ゴールデンの扱いは `plan.html` の「5. PR の段取り」。新しいパッケージ(`gui/widgets`・`gui/shell`)は
`pyproject.toml` の `packages` に足すこと。

## 進み具合

| PR | 状態 | メモ |
|---|---|---|
| 0 | マージ済み(#141) | 見本と計画の取り込み |
| 1 | マージ済み(#142) | テーマの土台。`gui/theme_color.py`(色の計算。判定は丸めた後の色で行う。見本の JavaScript は丸めで比が 4.4956 のように割ることがあった)、トークンを見本の値に、青の `selection_*` を廃止してテーマカラーの `accent` 系に統合(`accent_text` → `on_accent`、強調の色の文字は `accent_fg`)、QPalette をトークンから(ライトも)、設定 `theme_color`(既定 `#0F4C5C`、書き出しの対象)、`apply_theme(app, dark, theme_color=None)` の省略の条件に色、ミニマップの色をトークンから。`scripts/screenshot_ui.py` で見本と並べる画像を撮る |
| 2 | マージ済み(#143) | 新しい部品 `gui/widgets/`(画面にはまだ入れない)。`SegmentedControl`(文字・アイコン・線の見本)、`TypeTileGroup`、`SliderSpin`、`ColorChipRow`、`StatCard`、`SectionHeader`。どれも今の部品を値の持ち主にしたまま同期する: コンボは `ComboMirror`、スピンボックスは `SliderSpin` が中に取り込む。バインディングの「戻す」はシグナルを止めるので、戻したあと `refresh()` を呼ぶ。スイッチは部品を替えず `theme.make_toggle_switch(checkbox)`(プロキシスタイルが描く)。`scripts/screenshot_widgets.py` で部品だけを撮る |
| 3 | マージ済み(#144) | 上部バー(`gui/shell/header.py`。タブの帯を置くため `QTabWidget` を同じ呼び方の `ProjectTabs` に)・左端の帯・左パネルのデータセット(計画では PR 4 だったが、骨組みだけでは左が空になるので前倒し)・`gui/ui_mode.py`(表 `MODE_ONLY_ELEMENTS`、設定 `ui_mode`)。Windows はメニューバーを隠して ≡ に、ショートカットはタブに `addAction`。クイックアクセスは上部バーへ、管理は ≡ へ。一覧の下の1行の統計と高さの上限(175px)はやめた。キャンバスの幅が変わるので、画面の図をそのまま書き出す経路の図の大きさも変わる |
| 4 | マージ済み(#145) | 帯の残りのページ(`gui/shell/side_pages.py`): 解析(フィット・ピーク・よく使うデータ処理)・注釈・レイアウトは今の操作のボタンの並び(行はメニューと同じ QAction と同期する `QPushButton`。`QToolButton` は文字を左に寄せられない)。プラグインのパネルはドックをやめて「プラグイン」のページへ(`_plugin_panel_docks` → `_plugin_panels`、`area` は希望として受け取るだけ。`docs/plugin_development.md` も更新)。`screenshot_ui.py --pages` で各ページを撮る |
| 5 | マージ済み(#146) | グラフのカード(`builders/canvas_area.py`): 見出しの行(サブプロットのタイトル、無ければ「サブプロット N」・系列と点の数・リセット/ミニマップ/切り離し)、Advanced はプロットの上に文字付きのツール(`plot_toolbar`)、Lite は左に縦のアイコン(`plot_tool_rail`)。カーソルの吹き出しは「#行 · x · y」。統計のボタンと1行の統計はやめた |
| 6a | マージ済み(#147) | インスペクタ(`gui/shell/inspector.py`、幅 340px): 右のドックの中身をタブ「プロパティ / 軸 / 凡例(Advanced) / エクスポート」に。プロパティは対象の見出し+節(マーカーを独立した節に、節の見出しは `SectionHeader`、閉じた節には状態の要約)、軸は今の軸の設定(長い行は名前を上に折り返す `wrap_long_rows`)、凡例は軸の設定のフォームから凡例の行を移したもの、エクスポートはプレビューのドックをやめてタブに(`show_export_preview()` で前に出す)。上の階層の開閉(`collapsible_section_toggle`)は廃止。340px に収まるよう、長い項目のコンボは `cap_combo_width`、第2Y軸の数値欄は最小幅を指定、「2Dグリッドデータとして扱う」は「2Dグリッドとして扱う」に短縮 |
| 6b | マージ済み(#148) | プロパティの部品(`builders/property_widgets.py`): 線の種類のセグメント(`ComboMirror`、コンボは隠して欄の中に残す)、太さ・透明度の `SliderSpin`、平滑化のスイッチ、色のチップ(`ColorPickerWidget.show_quick_colors`、幅に入るだけ並べる)、シンプルの種類のタイル。バインディングで戻したあとは `refresh_property_widgets()`。シンプルの行と節は `ui_mode.LITE_HIDDEN_PROPERTY_FIELDS` / `LITE_PROPERTY_SECTIONS` で、種類などの今の条件のあとに `update_property_section_visibility` が隠す(モードを替えると `property_panel.update_mode_visibility()` で当て直す)。下に「アドバンスドですべて表示」の案内。名前の列は見本どおり 92px(長い名前は折り返す)。決定 7 の「線+点」は、Line がマーカーを描かない種類なので Line+Scatter にし、マーカーが無ければ円に(1つの「元に戻す」) |
| 7 | マージ済み(#149) | グラフの下のパネル(`gui/shell/bottom_panel.py`、アドバンスドだけ): グラフのカードと仕切り(`CenterSplitter`、つまみの横棒)で上下に分け、タブ「データ表・フィット結果・残差・来歴・ログ」。データ表は `gui/data_table_model.py`(読むだけ、行は visible_df、# は元の表の行の番号、フィットがあればフィット値・残差、負の残差は赤、カーソルで選んだ点の行に印)。フィット値は `core/analysis.evaluate_saved_fit()` で保存したパラメータから計算。元のデータを選んでも、そこから作ったフィットの結果を出す(`fit_result_for`)。フィット結果は `fit_info_textedit` をプロパティの「配置・情報」から移し、タブに R² のバッジ。残差・来歴のドックはやめてタブに(表示メニューはタブを開く項目、シンプルならアドバンスドに切り替える)。ログは `logging` のハンドラからこのウィンドウを開いてからの行。`DOCK_LAYOUT_VERSION` は 6。`screenshot_ui.py --bottom` でフィット付きの各タブを撮る。見本の絞り込みのボタンは未実装 |
| 8 | マージ済み(#150) | ステータスバー(`builders/canvas_area.setup_status_bar`): 左に「● 準備完了」と(アドバンスド)「N データセット · M 選択」、右に(アドバンスド)座標「X = …　Y = …」と「自動保存 N 分前 / たった今 / N 分ごと / オフ」(30 秒ごと・自動保存のたびに書き直す)。左の2つは通常の部品なので `showMessage()` の間は知らせに置き換わる。⚙ は `gui/shell/settings_popover.py` のポップアップ(プリセット8色・カスタム・ライト/ダークで使う色・読みやすさの調整の説明・既定に戻す・環境設定への入口)。色は `set_theme_color()`(`MainAppWindow` が全部のタブに当てる。タブの描き直しはダークモードと共通の `refresh_theme_colors()`)。環境設定の「外観」にもテーマカラー。`screenshot_ui.py --settings` |
| 9 | マージ済み(#151)。master へは #152 | 仕上げ: ドックレイアウトのプリセットを削除(決定 5。メニュー・`dock_layout` の関数・設定の行。サブメニューの GC の回帰テストは「エクスポート」に向け直した)、英語表示のテストを MainAppWindow で両モード(上部バー・⚙ のポップアップまで)、訳し漏れ(Undo履歴・無題のプロジェクト)、README(日本語・英語)の画面の説明、README とサイトの画像(`screenshot_ui.py --site`)、CHANGELOG の「未リリース」。macOS 実機の確認と Wiki はあとで(ユーザー)。プラグイン開発ハブには連絡済み |

CI の揺れ: `test_rendering[dark]` の画素(注釈のシナリオ)が CI だけで1回落ち、再実行で通った(PR 1)。master でも同じテストが時々落ちる(#137 で直したのはレイアウトの数値だけ)。続くようなら画素の比較にも許容を入れるか、画像を CI の成果物に残す。

macOS 実機の確認は PR ごとにせず、PR 9 にまとめる(2026-10-12 ユーザー指示)。

PR ごとの確認: `python scripts/screenshot_ui.py <出力フォルダ>` で撮った画像を、見本の同じ状態と並べてユーザーに見せ、OK をもらってから統合ブランチにマージする(2026-10-12 ユーザー指示)。
