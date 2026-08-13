# トラック3(残りの本体機能追加) 進捗管理

`Graphica_MASTER_SCHEDULE.md` のトラック3(3-1〜3-4、および未分類の残り項目)の進捗を記録する。
このファイルは各項目の「どう実装したか」の詳細ログ。**「今どこまで進んでいて次に何を
やるか」の短い要約は`CURRENT_STATE.md`を先に見ること**(新しいセッションはまず
`CURRENT_STATE.md`を読む運用)。このファイルは項目が完了するたびに追記していく
(上書きしない)。トラック1は`PLUGIN_API_PROGRESS.md`、トラック2は
`GUI_MODERNIZATION_PROGRESS.md`が同じ役割を持つ(対象トラックが異なるだけ)。

## トラック3-1: 解析基盤(優先度高、トラック2完了後すぐ着手)

| ID | 項目 | 状態 | 完了日 | 備考 |
|---|---|---|---|---|
| C-401 | フィット結果の構造化保持 | ✅ 完了 | 2026-08-13 | `core/analysis.py`の`calculate_curve_fit()`の戻り値をタプルからdict化(`popt`/`pcov`/`perr`/`param_names`/`x_fit`/`y_fit`/`r_squared`/`residuals`/`x_data_used`/`y_data_used`)。共分散行列(`pcov`)は従来`_`で捨てていたのを`perr = sqrt(diag(pcov))`として活用可能にした(C-405信頼帯の土台)。`core/dataset.py`の`Dataset`に`fit_result: dict`フィールドを追加(`fit_info`の表示用文字列とは別に、プログラムから再利用しやすい構造化データを保持)。`gui/mixins/dataset_mixin.py`の`_on_fit_curve`/`_on_batch_curve_fit`両方が`_build_fit_result_dict()`経由でJSON/pickle両対応のプレーンなdict(numpy型は全てPython組み込み型に変換済み)を組み立てて`Dataset.fit_result`に格納する。呼び出し側の戻り値アンパックが約20箇所(本体2箇所+テスト)あり、全て新形式に追従済み |
| C-308 | ベースライン補正(ALS/多項式/ラバーバンド/手動点) | ✅ 完了 | 2026-08-13 | `core/analysis.py`に4関数を新設: `calculate_baseline_als`(Eilers & Boelens法、2階差分の疎行列によるTikhonov正則化+非対称重み反復)、`calculate_baseline_polynomial`(Lieber & Mahadevan-Jansenの反復多項式フィット法/ModPoly)、`calculate_baseline_rubberband`(Andrewのmonotone chainによる下側凸包)、`calculate_baseline_manual`(指定アンカー点を線形補間の元データから求め、アンカー間を線形または3次スプラインで結ぶ)。4関数とも戻り値を`(x_sorted, baseline, corrected)`に統一。GUIは新設`BaselineCorrectionDialog`(`gui/dialogs.py`、手法をコンボボックス+`QStackedWidget`でパラメータ欄切替、`BatchExportDialog`と同じ構成)+`dataset_mixin.py`の`_on_baseline_correction_dataset`(既存の`_on_savgol_dataset`と同じ「カレント1件→非破壊で新規データセット追加」パターン、右クリックメニューの`Savitzky-Golayフィルタ...`の隣に追加)。ベースライン曲線自体を別データセットとして追加するオプション付き |
| C-907 | データセットの表示/非表示トグル(目アイコン) | 🟡 一部完了 | 2026-08-13 | ユーザー要望により3-1と同時並行で着手。**表示/非表示トグルのみ実装、検索・絞り込みは未着手**(roadmap #150はそのため`false`のまま)。`core/dataset.py`に`visible: bool`フィールド追加(既定True、後方互換)。`gui/canvas.py`の`MplCanvas.redraw_all()`冒頭で`visible=False`のデータセットを一括フィルタ(画面描画・エクスポート双方の唯一の入口のため、ここ1箇所で両方に効く)。`gui/minimap_widget.py`は`redraw_all`を経由しないため個別にフィルタを追加。UIはデータセットツリーに列を1つ追加(`gui/main_window.py`、`QHeaderView.ResizeMode.Stretch`/`Fixed`で列0=名前・列1=目アイコンの幅を固定)し、実体は`gui/dataset_style_icon.py`の`make_dataset_visibility_icon`/`apply_dataset_visibility_text_style`(非表示時は名前をグレーアウト)。クリック検知・Undo対応は`dataset_mixin.py`の`_on_dataset_tree_item_clicked`が既存の`_push_dataset_property_command`/`SetDatasetPropertiesCommand`パターンに乗せる形で実装(`_on_secondary_y_changed`と同じ構成)。アイコンは実物のTabler Icons SVG(`assets/icons/eye.svg`、MIT、`eye-off.svg`は既存流用)を使用 |

**3-1残り(未着手)**: C-403(パラメータ初期値・固定・範囲拘束UI)、C-305(共通X格子へのリサンプリング/補間)、C-311(区間積分)、C-411(ピーク定量表)、C-408(モデルライブラリ拡充)、C-405(信頼帯・予測帯の描画)、C-406(残差プロット)、C-413(フィット結果の出力)。
